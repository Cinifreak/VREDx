# VredX Example Materials

Validated `.mtlx` samples covering common MaterialX patterns in VRED 2027.
Open from the editor **Examples** menu or via **Open…**.

Regenerate after editing builders:

```
python tests/generate_examples.py
```

| File | Category | Description | Notes |
|------|----------|-------------|-------|
| `bxdf_carpaint_clearcoat.mtlx` | BxDF | Metallic carpaint + clearcoat |  |
| `bxdf_disney_principled.mtlx` | BxDF | Disney Principled diffuse |  |
| `bxdf_gltf_metallic.mtlx` | BxDF | glTF metallic-roughness gold |  |
| `bxdf_lama_mix_metals.mtlx` | BxDF | LamaMix diffuse + conductor stack |  |
| `bxdf_open_pbr_basic.mtlx` | BxDF | OpenPBR surface basics |  |
| `bxdf_standard_surface_emission.mtlx` | BxDF | Emissive standard_surface |  |
| `bxdf_standard_surface_glass.mtlx` | BxDF | Transmission glass with IOR |  |
| `bxdf_standard_surface_metal_aniso.mtlx` | BxDF | Anisotropic brushed metal |  |
| `bxdf_standard_surface_opacity.mtlx` | BxDF | Semi-transparent opacity |  |
| `bxdf_standard_surface_plastic.mtlx` | BxDF | Matte plastic standard_surface |  |
| `bxdf_standard_surface_thin_film.mtlx` | BxDF | Thin-film interference (GI raytracing) |  |
| `bxdf_surface_unlit.mtlx` | BxDF | Unlit emissive surface |  |
| `bxdf_usd_preview_surface.mtlx` | BxDF | USD Preview Surface with clearcoat |  |
| `geomprop_vertex_ao.mtlx` | Scene data | Vertex AO via geompropvalue (Raytracing/Vulkan) |  |
| `geomprop_vertex_color.mtlx` | Scene data | Vertex color lookup |  |
| `geomprop_world_position.mtlx` | Scene data | World position as base color |  |
| `limitation_displacement_height.mtlx` | Limitation | Displacement hookup (broken in VRED) | MaterialX displacement is known to be broken in VRED (Autodesk, Jan 2026). The material will load but displacement may not render.; Displacement connected to surfacematerial: VRED's MaterialX displacement support is currently broken. |
| `math_mix_float.mtlx` | Math | mix between two constant colors |  |
| `math_separate_combine.mtlx` | Math | separate3 / combine3 channel shuffle |  |
| `math_switch_colors.mtlx` | Math | switch node between color inputs |  |
| `npr_gooch_shading.mtlx` | NPR | Gooch shading into base_color |  |
| `procedural_cell_noise.mtlx` | Procedural | cellnoise2d mixed between two colors |  |
| `procedural_checkerboard.mtlx` | Procedural | Checkerboard base color |  |
| `procedural_fractal_marble.mtlx` | Procedural | fractal3d marble-like pattern |  |
| `procedural_noise_ramp.mtlx` | Procedural | noise2d color pattern on default UVs |  |
| `texture_image_pbr_maps.mtlx` | Texture | Image map slots for full PBR | Image node has no file set; it will sample its default color.; Image node has no file set; it will sample its default color. |
| `texture_normal_from_height.mtlx` | Texture | Height map to normal via heighttonormal | Image node has no file set; it will sample its default color. |
| `texture_tiled_checker.mtlx` | Texture | Tiled image with UV scale | Image node has no file set; it will sample its default color. |
| `texture_triplanar_defaults.mtlx` | Texture | Triplanar projection default colors |  |
| `texture_uv_transform_noise.mtlx` | Texture | UV scale + rotate2d + noise2d |  |

