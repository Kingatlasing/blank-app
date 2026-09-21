import streamlit as st
import streamlit.components.v1 as components

from app.voxelcraft import exporters, image_generator, text_generator
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

st.title("🧱 VoxelCraft")
st.caption("Describe anything and get a blocky, Minecraft-style 3D model — or turn a reference image into one.")

if "voxels" not in st.session_state:
    st.session_state.voxels = None
    st.session_state.note = None

with st.sidebar:
    st.header("Generate")
    mode = st.radio(
        "Source",
        ["Text prompt", "Reference image (+ optional prompt)"],
        help="Text prompt always works. An image is an optional way to steer the model instead.",
    )

    prompt = st.text_input(
        "Prompt",
        placeholder="a red house with a garden, a diamond sword, a purple dragon...",
    )

    image_bytes = None
    if mode.startswith("Reference image"):
        img_source = st.radio("Image source", ["From a URL", "Upload a file"], horizontal=True)
        image_url = ""
        uploaded = None
        if img_source == "From a URL":
            image_url = st.text_input("Image URL", placeholder="https://example.com/photo.png")
        else:
            uploaded = st.file_uploader("Upload image", type=["png", "jpg", "jpeg", "gif", "webp"])
        relief_mode = st.select_slider(
            "Depth style", options=["Flat pixel art", "3D relief"], value="3D relief"
        )
        img_resolution = st.slider("Image detail (pixels wide)", 8, 64, 28)

    st.divider()
    scale_factor = st.slider("Chunkiness (block size)", 1, 4, 2, help="How many voxels wide each block is.")
    generate = st.button("✨ Generate model", type="primary", use_container_width=True)

if generate:
    try:
        if mode == "Text prompt":
            if not prompt.strip():
                st.sidebar.error("Type a prompt first.")
            else:
                voxels, note = text_generator.generate_from_text(prompt)
                voxels = normalize(scale_voxels(voxels, scale_factor))
                voxels, truncated = voxel_count_limit(voxels, MAX_VOXELS)
                st.session_state.voxels = voxels
                st.session_state.note = note + (" (truncated — try a smaller chunkiness)" if truncated else "")
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
                internal_mode = "flat" if relief_mode == "Flat pixel art" else "relief"
                voxels = image_generator.image_to_voxels(image, resolution=img_resolution, mode=internal_mode)
                voxels = normalize(scale_voxels(voxels, scale_factor))
                voxels, truncated = voxel_count_limit(voxels, MAX_VOXELS)
                st.session_state.voxels = voxels
                note = f"Built from your reference image ({len(voxels)} voxels)."
                st.session_state.note = note + (" (truncated — lower the detail slider)" if truncated else "")
                st.session_state.title = prompt.strip() or "image model"
    except Exception as exc:  # noqa: BLE001 - surface any generation failure to the user
        st.sidebar.error(f"Couldn't generate a model: {exc}")

voxels = st.session_state.voxels

if voxels is None:
    st.info("👈 Enter a prompt (or a reference image) in the sidebar and click **Generate model** to get started.")
    st.markdown(
        """
**Try prompts like:**
- `a blue house with a red roof`
- `a diamond sword`
- `a green dragon` *(falls back to an abstract sculpture — still unique per prompt!)*
- `a snowy pine tree`
- `a golden castle`
- `a orange cat`

**Or switch to "Reference image"** and paste an image URL (or upload a photo) to turn it into a voxel sculpture.
        """
    )
else:
    st.success(st.session_state.note)
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
    "Everything above runs locally with rule-based procedural generation and image "
    "quantization — no external AI service required. Colors are matched to real "
    "Minecraft blocks so the .mcfunction export builds with vanilla blocks."
)
