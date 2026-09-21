import streamlit as st
import streamlit.components.v1 as components

from app.voxelcraft import exporters, image_generator, research, text_generator
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

MAX_VOXELS = 40_000

_DEPTH_STYLES = {
    "Flat pixel art": "flat",
    "3D relief": "relief",
    "3D revolve (round objects)": "revolve",
}


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_research(prompt: str):
    """Cache research lookups by prompt text so re-generating the same
    prompt doesn't re-hit Wikipedia/Openverse every time."""
    result = research.research_reference_image(prompt)
    if result is None:
        return None
    return (
        result.image, result.subject, result.source_label, result.source_url,
        result.build_method, result.reason,
    )


st.title("🧱 VoxelCraft")
st.caption(
    "Describe any object or building and get a blocky, Minecraft-style 3D voxel model, built from "
    "VoxelCraft's own procedural shapes. Optionally, turn on online photo research (or supply your "
    "own reference image) to steer the model from a real picture instead."
)

if "voxels" not in st.session_state:
    st.session_state.voxels = None
    st.session_state.note = None
    st.session_state.source_caption = None
    st.session_state.source_url = None

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
    img_source = None
    image_url = ""
    uploaded = None
    remove_bg = True

    if mode == "Text prompt":
        research_online = st.checkbox(
            "🔎 Optional: research a reference photo online",
            value=False,
            help="Off by default — generation uses VoxelCraft's own built-in procedural shapes. Turn "
                 "this on to instead look up a real photo of your subject (Wikipedia, then Openverse), "
                 "read what kind of object it is to decide whether to reconstruct it as a lathed 3D "
                 "revolve (towers, bottles, trees, ...) or a relief sculpture (buildings, animals, "
                 "vehicles, ...), and build from that. Falls back to the procedural shapes if nothing "
                 "usable is found.",
        )
    else:
        img_source = st.radio("Image source", ["From a URL", "Upload a file"], horizontal=True)
        if img_source == "From a URL":
            image_url = st.text_input("Image URL", placeholder="https://example.com/photo.png")
        else:
            uploaded = st.file_uploader("Upload image", type=["png", "jpg", "jpeg", "gif", "webp"])

    show_resolution = mode.startswith("Reference image") or research_online
    if show_resolution:
        img_resolution = st.slider("Image detail (pixels wide)", 8, 64, 28)
    else:
        img_resolution = 28

    if mode.startswith("Reference image"):
        depth_style = st.select_slider("3D reconstruction method", options=list(_DEPTH_STYLES), value="3D relief")
        remove_bg = st.checkbox("Remove background first", value=True)
    else:
        depth_style = "3D relief"

    st.divider()
    scale_factor = st.slider("Chunkiness (block size)", 1, 4, 2, help="How many voxels wide each block is.")
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

                if research_online:
                    with st.spinner(f"Researching '{prompt}' online and working out how to build it in 3D..."):
                        cached = _cached_research(prompt)
                    if cached is not None:
                        image, subject, source_label, source_url, build_method, reason = cached
                        voxels = image_generator.image_to_voxels(
                            image, resolution=img_resolution, mode=build_method, remove_bg=True
                        )
                        method_label = {"revolve": "a lathed 3D revolve", "relief": "a 3D relief sculpture"}[build_method]
                        note = f"Researched '{subject}' online and built {method_label} from a real photo ({reason})."
                        source_caption = f"Reference photo: {source_label}"

                if voxels is None:
                    voxels, note = text_generator.generate_from_text(prompt)
                    if research_online:
                        note = "No usable reference photo found online, so " + note[0].lower() + note[1:]

                voxels = normalize(scale_voxels(voxels, scale_factor))
                voxels, truncated = voxel_count_limit(voxels, MAX_VOXELS)
                st.session_state.voxels = voxels
                st.session_state.note = note + (" (truncated — try a smaller chunkiness)" if truncated else "")
                st.session_state.source_caption = source_caption
                st.session_state.source_url = source_url
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
- `a diamond sword`
- `a golden castle`
- `a snowy pine tree`
- `a green dragon` *(falls back to an abstract sculpture — still unique per prompt!)*

By default, prompts are built entirely from VoxelCraft's own procedural shape library — no internet
required. Flip on **"🔎 Optional: research a reference photo online"** in the sidebar to instead have
VoxelCraft look up a real photo (Wikipedia, then Openverse), work out how to build it in 3D from that
photo (a lathed revolve for anything round about a vertical axis, like towers or bottles; a relief
sculpture otherwise), and sculpt the model from it. Or switch to "Reference image" to supply — and
steer the reconstruction of — your own photo directly.
        """
    )
else:
    st.success(st.session_state.note)
    if st.session_state.source_caption:
        if st.session_state.source_url:
            st.caption(f"{st.session_state.source_caption} — [source]({st.session_state.source_url})")
        else:
            st.caption(st.session_state.source_caption)

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
        st.download_button(
            "⬇️ Download .mcfunction",
            data=mcfunction,
            file_name="build.mcfunction",
            mime="text/plain",
            use_container_width=True,
            help="Drop into a datapack's data/<namespace>/functions/ folder, "
                 "then run /function <namespace>:build in Minecraft Java Edition "
                 "while standing where you want the model to appear.",
        )
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
    "no internet or AI API needed. Online photo research is entirely optional: when turned on, it looks "
    "up a real reference photo (Wikipedia, then Openverse — both free, keyless, openly-licensed sources), "
    "reads the article text to pick a 3D reconstruction method (a lathed revolve for axially-symmetric "
    "subjects, a relief sculpture otherwise), and sculpts the photo into voxels quantized to real "
    "Minecraft block colors. If it's off, finds nothing, or you're offline, VoxelCraft falls back to its "
    "built-in procedural shapes so generation never fails outright."
)
