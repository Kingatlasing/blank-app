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


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_research(prompt: str):
    """Cache research lookups by prompt text so re-generating the same
    prompt doesn't re-hit Wikipedia/Openverse every time."""
    result = research.research_reference_image(prompt)
    if result is None:
        return None
    return result.image, result.subject, result.source_label, result.source_url


st.title("🧱 VoxelCraft")
st.caption(
    "Describe any object or building — VoxelCraft researches a real reference photo for it online "
    "(Wikipedia, then Openverse) and sculpts a blocky 3D Minecraft-style model from it. "
    "You can also supply your own reference image instead."
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
        help="Text prompt researches a photo online for you. An image lets you supply your own instead.",
    )

    prompt = st.text_input(
        "Prompt",
        placeholder="the Eiffel Tower, a golden retriever, a red barn, a diamond sword...",
    )

    research_online = False
    img_source = None
    image_url = ""
    uploaded = None

    if mode == "Text prompt":
        research_online = st.checkbox(
            "🔎 Research a reference photo online first",
            value=True,
            help="Looks up a real photo of your subject (Wikipedia, then Openverse) and builds the "
                 "model from it. If nothing is found (or you're offline), falls back to VoxelCraft's "
                 "built-in procedural shapes.",
        )
    else:
        img_source = st.radio("Image source", ["From a URL", "Upload a file"], horizontal=True)
        if img_source == "From a URL":
            image_url = st.text_input("Image URL", placeholder="https://example.com/photo.png")
        else:
            uploaded = st.file_uploader("Upload image", type=["png", "jpg", "jpeg", "gif", "webp"])

    show_image_controls = mode.startswith("Reference image") or research_online
    if show_image_controls:
        relief_mode = st.select_slider(
            "Depth style", options=["Flat pixel art", "3D relief"], value="3D relief"
        )
        img_resolution = st.slider("Image detail (pixels wide)", 8, 64, 28)
    else:
        relief_mode = "3D relief"
        img_resolution = 28

    st.divider()
    scale_factor = st.slider("Chunkiness (block size)", 1, 4, 2, help="How many voxels wide each block is.")
    generate = st.button("✨ Generate model", type="primary", use_container_width=True)

if generate:
    try:
        internal_mode = "flat" if relief_mode == "Flat pixel art" else "relief"

        if mode == "Text prompt":
            if not prompt.strip():
                st.sidebar.error("Type a prompt first.")
            else:
                voxels = None
                note = None
                source_caption = None
                source_url = None

                if research_online:
                    with st.spinner(f"Researching a reference photo for '{prompt}'..."):
                        cached = _cached_research(prompt)
                    if cached is not None:
                        image, subject, source_label, source_url = cached
                        voxels = image_generator.image_to_voxels(
                            image, resolution=img_resolution, mode=internal_mode
                        )
                        note = f"Researched '{subject}' online and sculpted a 3D model from a real photo."
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
                voxels = image_generator.image_to_voxels(image, resolution=img_resolution, mode=internal_mode)
                voxels = normalize(scale_voxels(voxels, scale_factor))
                voxels, truncated = voxel_count_limit(voxels, MAX_VOXELS)
                st.session_state.voxels = voxels
                note = f"Built from your reference image ({len(voxels)} voxels)."
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
- `the Eiffel Tower`
- `a golden retriever`
- `a red barn`
- `a diamond sword` *(no great photo online → falls back to a built-in procedural shape)*
- `a snowy pine tree`
- `a green dragon` *(falls back to an abstract sculpture — still unique per prompt!)*

Each one is **researched online first** (a real photo, via Wikipedia/Openverse) and sculpted into a
voxel model — turn the checkbox off in the sidebar to use only VoxelCraft's built-in procedural shapes,
or switch to "Reference image" to supply your own photo instead.
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
    "Text prompts are researched online (Wikipedia, then Openverse — both free, keyless, openly-licensed "
    "sources) for a real reference photo, which is quantized to real Minecraft block colors and sculpted "
    "into voxels. If research is off, finds nothing, or you're offline, VoxelCraft falls back to its "
    "built-in rule-based procedural shapes so generation never fails outright. No paid AI API is used."
)
