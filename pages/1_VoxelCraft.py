import streamlit as st
import streamlit.components.v1 as components

from app.voxelcraft import exporters, image_generator, llm_builder, local_library, research, text_generator
from app.voxelcraft.transform import normalize, scale_voxels, voxel_count_limit
from app.voxelcraft.viewer import build_viewer_html

st.set_page_config(page_title="VoxelCraft", page_icon="🧱", layout="wide")

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
        iframe {border: none; border-radius: 10px;}
    </style>
    """,
    unsafe_allow_html=True,
)

MAX_VOXELS = 80_000

_DEPTH_STYLES = {
    "Flat pixel art": "flat",
    "3D relief": "relief",
    "3D revolve (round objects)": "revolve",
}


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_research(prompt: str):
    """Cache research lookups by prompt text so re-generating the same
    prompt doesn't re-hit Wikipedia/Openverse/Wikidata every time."""
    result = research.research_reference_image(prompt)
    if result is None:
        return None
    return (
        result.image, result.subject, result.source_label, result.source_url,
        result.build_method, result.reason, result.facts, result.origin,
    )


st.title("🧱 VoxelCraft")
st.caption(
    "Describe any object or building and get a blocky, Minecraft-style 3D voxel model, built from "
    "VoxelCraft's own procedural shapes. Optionally, research a real reference photo + dimensions "
    "online, hand design off to your own local Ollama model, or supply your own reference image."
)

if "voxels" not in st.session_state:
    st.session_state.voxels = None
    st.session_state.note = None
    st.session_state.source_caption = None
    st.session_state.source_url = None
    st.session_state.blueprint_caption = None
    st.session_state.llm_code = None

with st.sidebar:
    st.header("Generate")
    mode = st.radio(
        "Source",
        ["Text prompt", "Reference image (+ optional prompt)"],
        help="Text prompt builds from VoxelCraft's procedural shapes (with optional online photo "
             "research). An image lets you supply your own reference photo instead.",
    )

    prompt = st.text_input(
        "Prompt",
        placeholder="the Eiffel Tower, a golden retriever, a red barn, a diamond sword...",
    )

    research_online = False
    use_llm = False
    ollama_host = "http://localhost:11434"
    ollama_model = "qwen2.5-coder"
    img_source = None
    image_url = ""
    uploaded = None
    remove_bg = True

    if mode == "Text prompt":
        gen_strategy = st.radio(
            "How should VoxelCraft build it?",
            [
                "Built-in procedural shapes",
                "🔎 Research a reference photo + dimensions online",
                "🧠 Design a custom structure with a local LLM (Ollama)",
            ],
            help="Procedural: VoxelCraft's own shape library, fully offline. Research: look up a real "
                 "photo (Wikipedia/Openverse) and real dimensions (Wikidata). LLM: ask your local "
                 "Ollama model to design something genuinely custom, beyond the shape library.",
        )
        research_online = gen_strategy.startswith("🔎")
        if research_online:
            bundled_photos, cached_facts = local_library.library_status()
            if bundled_photos or cached_facts:
                st.caption(
                    f"Bundled offline: {bundled_photos} reference photo(s) and {cached_facts} set(s) of "
                    "real-world dimensions, checked before any network lookup."
                )
            else:
                st.caption(
                    "The bundled reference library is empty — every lookup will go to the network. "
                    "Run `python tools/ingest_library.py` to populate it."
                )
        use_llm = gen_strategy.startswith("🧠")
        llm_method = "Write code (recommended)"
        if use_llm:
            ollama_host = st.text_input("Ollama host", value="http://localhost:11434")
            ollama_model = st.text_input("Ollama model", value="qwen2.5-coder")
            st.caption(
                "Sends your prompt to that local Ollama server, which writes Python code against a "
                "small geometry API (box/sphere/cylinder/cone/merge). That code runs in a restricted "
                "sandbox here (no imports, no file/network access, 5s execution limit) to produce the "
                "model. Can take a while on modest hardware. Falls back to procedural shapes if Ollama "
                "is unreachable or produces nothing usable."
            )
            use_direct_enumeration = st.checkbox(
                "⚙️ Advanced: have it hand-enumerate coordinates instead of writing code",
                value=False,
                help="Off by default (writing code is more precise and scales to complex shapes). "
                     "Turning this on asks the model to list every voxel's (x, y, z, color) directly, "
                     "no code involved — simpler, but slower, capped at a few thousand voxels, and "
                     "much less exact since it's the model eyeballing coordinates one at a time rather "
                     "than computed geometry.",
            )
            if use_direct_enumeration:
                llm_method = "Hand-enumerate coordinates"
    else:
        img_source = st.radio("Image source", ["From a URL", "Upload a file"], horizontal=True)
        if img_source == "From a URL":
            image_url = st.text_input("Image URL", placeholder="https://example.com/photo.png")
        else:
            uploaded = st.file_uploader("Upload image", type=["png", "jpg", "jpeg", "gif", "webp"])

    # Fixed for now (sliders removed while stabilizing generation quality —
    # to be reintroduced once research mode is reliable).
    img_resolution = 28
    scale_factor = 2

    if mode.startswith("Reference image"):
        depth_style = st.select_slider("3D reconstruction method", options=list(_DEPTH_STYLES), value="3D relief")
        remove_bg = st.checkbox("Remove background first", value=True)
    else:
        depth_style = "3D relief"

    st.divider()
    generate = st.button("✨ Generate model", type="primary", use_container_width=True)

if generate:
    try:
        manual_mode = _DEPTH_STYLES[depth_style]

        if mode == "Text prompt":
            if not prompt.strip():
                st.sidebar.error("Type a prompt first.")
            else:
                voxels = None
                note = None
                source_caption = None
                source_url = None
                blueprint_caption = None
                llm_code = None
                degenerate_photo = False

                if use_llm:
                    spinner_msg = (
                        f"Asking {ollama_model} (via Ollama) to design a custom structure — "
                        "this can take a while on local hardware..."
                    )
                    with st.spinner(spinner_msg):
                        try:
                            if llm_method.startswith("Write code"):
                                voxels, note, llm_code = llm_builder.generate_llm_structure(
                                    prompt, model=ollama_model, host=ollama_host
                                )
                            else:
                                voxels, note = llm_builder.generate_llm_structure_direct(
                                    prompt, model=ollama_model, host=ollama_host
                                )
                        except llm_builder.LLMBuildError as exc:
                            st.sidebar.warning(f"LLM design failed ({exc}) — falling back to built-in procedural shapes.")

                if research_online and voxels is None:
                    with st.spinner(f"Researching '{prompt}' online and working out how to build it in 3D..."):
                        cached = _cached_research(prompt)
                    if cached is not None:
                        image, subject, source_label, source_url, build_method, reason, facts, origin = cached
                        researched_voxels = image_generator.image_to_voxels(
                            image, resolution=img_resolution, mode=build_method,
                            remove_bg=True, target_ratio=facts.ratio,
                        )
                        # relief/flat color each voxel individually from the photo, so a
                        # near-single-color result means the reconstruction went wrong
                        # somewhere upstream (bad background removal, a decoding issue,
                        # ...) rather than a faithful build — don't ship an unrecognizable
                        # colored blob as "the answer". (revolve legitimately averages
                        # colors per row, so a uniform result there can be correct.)
                        degenerate_photo = build_method != "revolve" and image_generator.is_degenerate(researched_voxels)
                        if not degenerate_photo:
                            voxels = researched_voxels
                            method_label = {"revolve": "a lathed 3D revolve", "relief": "a 3D relief sculpture"}[build_method]
                            found = ("from the bundled reference library" if origin == "library"
                                     else "online")
                            note = f"Researched '{subject}' {found} and built {method_label} from a real photo ({reason})."
                            source_caption = f"Reference photo: {source_label}"
                            if facts.summary():
                                # facts.source, not a hard-coded "Wikidata": these
                                # numbers come from the curated landmark table
                                # whenever Wikidata has no entry or isn't reachable.
                                facts_source = facts.source or "real-world reference data"
                                note += f" Proportions corrected using real-world dimensions from {facts_source}."
                                blueprint_caption = f"Blueprint data ({facts_source}): {facts.summary()}"

                if voxels is None:
                    voxels, note = text_generator.generate_from_text(prompt)
                    if degenerate_photo:
                        note = ("The researched photo didn't reconstruct well (came out nearly "
                                 "one solid color), so ") + note[0].lower() + note[1:]
                    elif research_online:
                        note = "No usable reference photo found online, so " + note[0].lower() + note[1:]
                    elif use_llm:
                        note = "Falling back to a procedural shape: " + note[0].lower() + note[1:]

                voxels = normalize(scale_voxels(voxels, scale_factor))
                voxels, truncated = voxel_count_limit(voxels, MAX_VOXELS)
                st.session_state.voxels = voxels
                st.session_state.note = note + (" (truncated — try a smaller chunkiness)" if truncated else "")
                st.session_state.source_caption = source_caption
                st.session_state.source_url = source_url
                st.session_state.blueprint_caption = blueprint_caption
                st.session_state.llm_code = llm_code
                st.session_state.title = prompt
        else:
            image = None
            if img_source == "From a URL":
                if not image_url.strip():
                    st.sidebar.error("Paste an image URL first.")
                else:
                    with st.spinner("Downloading image..."):
                        image = image_generator.fetch_image_from_url(image_url.strip())
            elif uploaded is not None:
                image = image_generator.load_image_from_bytes(uploaded.read())
            else:
                st.sidebar.error("Upload an image or paste a URL first.")

            if image is not None:
                voxels = image_generator.image_to_voxels(
                    image, resolution=img_resolution, mode=manual_mode, remove_bg=remove_bg
                )
                voxels = normalize(scale_voxels(voxels, scale_factor))
                voxels, truncated = voxel_count_limit(voxels, MAX_VOXELS)
                st.session_state.voxels = voxels
                note = f"Built from your reference image using {depth_style.lower()} ({len(voxels)} voxels)."
                st.session_state.note = note + (" (truncated — lower the detail slider)" if truncated else "")
                st.session_state.source_caption = None
                st.session_state.source_url = None
                st.session_state.blueprint_caption = None
                st.session_state.llm_code = None
                st.session_state.title = prompt.strip() or "image model"
    except Exception as exc:  # noqa: BLE001 - surface any generation failure to the user
        st.sidebar.error(f"Couldn't generate a model: {exc}")

voxels = st.session_state.voxels

if voxels is None:
    st.info("👈 Enter a prompt in the sidebar and click **Generate model** to get started.")
    st.markdown(
        """
**Try prompts like:**
- `a red house with a garden`
- `a house with two floors and a spiral staircase`
- `a fully realistic heart` *(a real 3D heart-surface solid, not a flat cutout)*
- `a Greek temple` *(has a genuinely hollow, walkable interior)*
- `a witch's castle with a knight and dragon` *(composes all three into one scene)*
- `a snowy pine tree`
- `a fluffy cloud` *(no exact match — falls back to an abstract sculpture, still unique per prompt!)*

By default, prompts are built entirely from VoxelCraft's own procedural shape library — no internet
required. In the sidebar, **"How should VoxelCraft build it?"** offers two alternatives: **🔎 Research
online** looks up a real photo (Wikipedia, then Openverse), works out how to build it in 3D from that
photo (a lathed revolve for anything round about a vertical axis; a relief sculpture otherwise), and
pulls real height/width/floor-count facts from Wikidata to correct the proportions. **🧠 Design with a
local LLM** sends your prompt to your own Ollama server, which writes Python code against a small
geometry API to design something genuinely custom, beyond the shape library — run in a restricted
local sandbox to build the model. Every model exports as a literal, ordered `.mcfunction` build
sequence. Or switch to "Reference image" to supply — and steer the reconstruction of — your own photo
directly.
        """
    )
else:
    st.success(st.session_state.note)
    if st.session_state.source_caption:
        if st.session_state.source_url:
            st.caption(f"{st.session_state.source_caption} — [source]({st.session_state.source_url})")
        else:
            st.caption(st.session_state.source_caption)
    if st.session_state.blueprint_caption:
        st.caption(st.session_state.blueprint_caption)
    if st.session_state.llm_code:
        with st.expander("🧠 Code the LLM wrote for this structure"):
            st.code(st.session_state.llm_code, language="python")

    col_view, col_export = st.columns([3, 1])

    with col_view:
        components.html(build_viewer_html(voxels), height=620, scrolling=False)

    with col_export:
        st.subheader("Export")
        st.metric("Voxel count", len(voxels))
        st.download_button(
            "⬇️ Download JSON",
            data=exporters.to_json(voxels),
            file_name="model.json",
            mime="application/json",
            use_container_width=True,
        )
        obj_text, mtl_text = exporters.to_obj(voxels)
        st.download_button(
            "⬇️ Download OBJ mesh",
            data=obj_text,
            file_name="model.obj",
            mime="text/plain",
            use_container_width=True,
        )
        st.download_button(
            "⬇️ Download MTL colors",
            data=mtl_text,
            file_name="model.mtl",
            mime="text/plain",
            use_container_width=True,
        )
        mcfunction = exporters.to_mcfunction(voxels)
        step_count = sum(1 for line in mcfunction.splitlines() if line.startswith("fill "))
        st.download_button(
            "⬇️ Download .mcfunction (assembly instructions)",
            data=mcfunction,
            file_name="build.mcfunction",
            mime="text/plain",
            use_container_width=True,
            help="A literal, ordered list of block-placement commands that assembles the model — "
                 "drop into a datapack's data/<namespace>/functions/ folder, then run "
                 "/function <namespace>:build in Minecraft Java Edition while standing where you "
                 "want the model to appear.",
        )
        with st.expander(f"📋 Preview build steps ({step_count} placement commands)"):
            st.caption(
                "This is the actual construction sequence — each line places one run of real "
                "Minecraft blocks. Run the whole file in-game (see below) to build it automatically, "
                "or follow it by hand as an assembly guide."
            )
            st.code("\n".join(mcfunction.splitlines()[:40]), language=None)
            if step_count > 38:
                st.caption(f"...and {step_count - 38} more steps in the downloaded file.")
        with st.expander("How do I use the .mcfunction in real Minecraft?"):
            st.markdown(
                """
1. Create a datapack: `<world>/datapacks/voxelcraft/data/voxelcraft/functions/build.mcfunction`
   and paste the downloaded file's contents into it (plus a
   `pack.mcmeta` — see the [datapack docs](https://minecraft.wiki/w/Data_pack)).
2. In-world, run `/reload`.
3. Stand where you want the model's corner to appear and run
   `/function voxelcraft:build`.
                """
            )

st.divider()
st.caption(
    "By default, everything above runs locally with VoxelCraft's own rule-based procedural shapes — "
    "no internet or AI API needed. Online research is optional: when turned on, it looks up a real "
    "reference photo (Wikipedia, then Openverse — both free, keyless, openly-licensed sources), reads "
    "the article text to pick a 3D reconstruction method, pulls real dimensions from Wikidata, and "
    "sculpts the photo into voxels. The local-LLM option is also optional: it sends your prompt to your "
    "own Ollama server, which writes Python code against a small geometry API; that code runs in a "
    "restricted local sandbox (no imports, no file/network access, a hard execution-time limit) to "
    "produce the model. In every case, if the chosen option is off, unreachable, or finds/produces "
    "nothing usable, VoxelCraft falls back to its built-in procedural shapes so generation never fails "
    "outright."
)
