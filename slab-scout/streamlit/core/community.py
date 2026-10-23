"""Shared community catalog + vault.

With a free Supabase project configured, every confirmed scan, reported fake and
added sale is shared with everyone using the app, so identification and pricing
improve as people use it. Without it, the same features work on this device
only (a local SQLite file).
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

import requests


def card_key(c: dict) -> str:
    parts = [c.get("game", ""), c.get("name", ""), c.get("set", ""), c.get("number", ""), c.get("variant", "")]
    return "|".join(" ".join(str(p).lower().split()) for p in parts)


CATALOG_FIELDS = ["id", "card_key", "game", "name", "set_name", "number", "year", "brand", "rarity", "variant",
                  "card_type", "phash", "thumb", "source", "confirmations", "is_fake", "fake_reasons", "created_at"]


class Store:
    def __init__(self, supabase_url: str = "", supabase_key: str = "", local_path: str = "slabscout.db"):
        self.url = (supabase_url or "").rstrip("/")
        self.key = supabase_key or ""
        self.shared = bool(self.url and self.key)
        if not self.shared:
            self.db = sqlite3.connect(local_path, check_same_thread=False)
            self._init_local()

    # ---------- plumbing ----------
    def _h(self, extra: dict | None = None) -> dict:
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        h.update(extra or {})
        return h

    def _rest(self, method: str, path: str, **kw):
        r = requests.request(method, f"{self.url}/rest/v1/{path}", headers=self._h(kw.pop("headers", None)), timeout=20, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"Community database error {r.status_code}: {r.text[:200]}")
        return r.json() if r.text else None

    def _rpc(self, fn: str, args: dict):
        return self._rest("POST", f"rpc/{fn}", data=json.dumps(args))

    def _init_local(self):
        self.db.executescript(
            """
            create table if not exists catalog_cards (id text primary key, card_key text, game text, name text, set_name text,
              number text, year text, brand text, rarity text, variant text, card_type text, phash text, thumb text, source text,
              confirmations integer default 1, is_fake integer default 0, fake_reasons text, created_at real);
            create table if not exists catalog_sales (id text primary key, card_key text, grade text, price real, sold_on text,
              url text, created_at real);
            create table if not exists vault_cards (id text primary key, vault_code text, data text, created_at real);
            create table if not exists vault_history (vault_code text, day text, value real, primary key (vault_code, day));
            create table if not exists scan_corrections (id text primary key, phash text, catalog_key text, created_at real);
            """
        )
        self.db.commit()

    # ---------- catalog ----------
    def catalog_fingerprints(self, game: str = "") -> list[dict]:
        """Lightweight rows used to match a new scan by image fingerprint."""
        cols = "id,card_key,game,name,set_name,number,year,brand,rarity,variant,card_type,phash,thumb,confirmations,is_fake,fake_reasons"
        if self.shared:
            q = f"catalog_cards?select={cols}&phash=not.is.null&limit=5000"
            if game:
                q += f"&game=eq.{requests.utils.quote(game)}"
            return self._rest("GET", q) or []
        sql = f"select {cols} from catalog_cards where phash is not null" + (" and game=?" if game else "") + " limit 5000"
        cur = self.db.execute(sql, (game,) if game else ())
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]

    def add_card(self, card: dict, phash: str, thumb: str, source: str, is_fake: bool = False, fake_reasons: str = "") -> None:
        row = {
            "card_key": card_key(card) + ("|fake" if is_fake else ""), "game": card.get("game", ""), "name": card.get("name", ""),
            "set_name": card.get("set", ""), "number": card.get("number", ""), "year": card.get("year", ""),
            "brand": card.get("brand", ""), "rarity": card.get("rarity", ""), "variant": card.get("variant", ""),
            "card_type": card.get("card_type", ""), "phash": phash, "thumb": thumb, "source": source,
            "is_fake": is_fake, "fake_reasons": fake_reasons,
        }
        if self.shared:
            self._rpc("add_catalog_card", {"p": row})
            return
        cur = self.db.execute("select id from catalog_cards where card_key=?", (row["card_key"],)).fetchone()
        if cur:
            self.db.execute("update catalog_cards set confirmations=confirmations+1, phash=coalesce(phash, ?), thumb=coalesce(thumb, ?) where id=?",
                            (phash, thumb, cur[0]))
        else:
            self.db.execute(
                f"insert into catalog_cards ({','.join(['id', 'created_at'] + list(row))}) values ({','.join('?' * (len(row) + 2))})",
                [str(uuid.uuid4()), time.time()] + [int(v) if isinstance(v, bool) else v for v in row.values()],
            )
        self.db.commit()

    # ---------- corrections: the card a person picked for a scan (so the next look-alike scan gets it right) ----------
    def add_correction(self, phash: str, catalog_key: str) -> None:
        if not phash or not catalog_key:
            return
        if self.shared:
            try:
                self._rest("POST", "scan_corrections", data=json.dumps({"phash": phash[:64], "catalog_key": catalog_key[:500]}),
                           headers={"Prefer": "return=minimal"})
            except Exception:
                pass  # older database without the table: corrections stay off
            return
        self.db.execute("insert into scan_corrections (id, phash, catalog_key, created_at) values (?,?,?,?)",
                        (str(uuid.uuid4()), phash, catalog_key, time.time()))
        self.db.commit()

    def corrections(self, limit: int = 20000) -> list[dict]:
        if self.shared:
            try:
                return self._rest("GET", f"scan_corrections?select=phash,catalog_key&order=created_at.desc&limit={limit}") or []
            except Exception:
                return []
        cur = self.db.execute("select phash, catalog_key from scan_corrections order by created_at desc limit ?", (limit,))
        return [{"phash": a, "catalog_key": b} for a, b in cur.fetchall()]

    def search_catalog(self, text: str, limit: int = 30) -> list[dict]:
        text = text.strip()
        if self.shared:
            q = "catalog_cards?select=id,game,name,set_name,number,rarity,variant,brand,card_type,thumb,confirmations,is_fake,fake_reasons&order=confirmations.desc"
            if text:
                q += f"&or=(name.ilike.*{requests.utils.quote(text)}*,set_name.ilike.*{requests.utils.quote(text)}*)"
            return self._rest("GET", q + f"&limit={limit}") or []
        like = f"%{text}%"
        cur = self.db.execute(
            "select id,game,name,set_name,number,rarity,variant,brand,card_type,thumb,confirmations,is_fake,fake_reasons from catalog_cards "
            "where name like ? or set_name like ? order by confirmations desc limit ?", (like, like, limit))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def stats(self) -> dict:
        if self.shared:
            def count(t, f=""):
                r = requests.get(f"{self.url}/rest/v1/{t}?select=id{f}", headers=self._h({"Prefer": "count=exact", "Range": "0-0"}), timeout=15)
                try:
                    return int(r.headers.get("content-range", "*/0").split("/")[-1])
                except ValueError:
                    return 0
            return {"cards": count("catalog_cards", "&is_fake=eq.false"), "fakes": count("catalog_cards", "&is_fake=eq.true"), "sales": count("catalog_sales")}
        one = lambda q: self.db.execute(q).fetchone()[0]
        return {"cards": one("select count(*) from catalog_cards where is_fake=0"), "fakes": one("select count(*) from catalog_cards where is_fake=1"),
                "sales": one("select count(*) from catalog_sales")}

    # ---------- sales people report ----------
    def add_sale(self, card: dict, grade: str, price: float, sold_on: str, url: str) -> None:
        row = {"card_key": card_key(card), "grade": grade, "price": price, "sold_on": sold_on or None, "url": url}
        if self.shared:
            self._rest("POST", "catalog_sales", data=json.dumps(row))
            return
        self.db.execute("insert into catalog_sales (id,card_key,grade,price,sold_on,url,created_at) values (?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), row["card_key"], grade, price, sold_on, url, time.time()))
        self.db.commit()

    def sales_for(self, card: dict, limit: int = 30) -> list[dict]:
        k = card_key(card)
        if self.shared:
            return self._rest("GET", f"catalog_sales?select=grade,price,sold_on,url&card_key=eq.{requests.utils.quote(k)}&order=sold_on.desc.nullslast&limit={limit}") or []
        cur = self.db.execute("select grade,price,sold_on,url from catalog_sales where card_key=? order by sold_on desc limit ?", (k, limit))
        return [dict(zip(["grade", "price", "sold_on", "url"], r)) for r in cur.fetchall()]

    # ---------- personal vault (private, by vault code) ----------
    def vault_list(self, code: str) -> list[dict]:
        if not code:
            return []
        if self.shared:
            rows = self._rpc("vault_list", {"p_code": code}) or []
            return [{**(r.get("data") or {}), "id": r["id"]} for r in rows]
        cur = self.db.execute("select id,data from vault_cards where vault_code=? order by created_at desc", (code,))
        return [{**json.loads(d), "id": i} for i, d in cur.fetchall()]

    def vault_add(self, code: str, data: dict) -> None:
        if self.shared:
            self._rpc("vault_add", {"p_code": code, "p_data": data})
            return
        self.db.execute("insert into vault_cards (id,vault_code,data,created_at) values (?,?,?,?)", (str(uuid.uuid4()), code, json.dumps(data), time.time()))
        self.db.commit()

    def vault_update(self, code: str, card_id: str, data: dict) -> None:
        if self.shared:
            self._rpc("vault_update", {"p_code": code, "p_id": card_id, "p_data": data})
            return
        self.db.execute("update vault_cards set data=? where id=? and vault_code=?", (json.dumps(data), card_id, code))
        self.db.commit()

    # ---------- portfolio value history (one point per day) ----------
    def history_add(self, code: str, day: str, value: float) -> None:
        if self.shared:
            self._rpc("vault_history_add", {"p_code": code, "p_day": day, "p_value": value})
            return
        self.db.execute("insert or replace into vault_history (vault_code, day, value) values (?,?,?)", (code, day, value))
        self.db.commit()

    def history_list(self, code: str) -> list[dict]:
        if self.shared:
            return [{"day": r["day"], "value": float(r["value"])} for r in (self._rpc("vault_history_list", {"p_code": code}) or [])]
        cur = self.db.execute("select day, value from vault_history where vault_code=? order by day", (code,))
        return [{"day": d, "value": v} for d, v in cur.fetchall()]

    def vault_delete(self, code: str, card_id: str) -> None:
        if self.shared:
            self._rpc("vault_delete", {"p_code": code, "p_id": card_id})
            return
        self.db.execute("delete from vault_cards where id=? and vault_code=?", (card_id, code))
        self.db.commit()
