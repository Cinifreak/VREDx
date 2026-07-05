# VRED 2027 MaterialX Support Matrix

Compiled from the VRED Pro 2027 beta (VREDPro-19.1) installation, its
Python API documentation, and Autodesk staff statements on the VRED
forum. See [docs/SUPPORT_MATRIX.md](docs/SUPPORT_MATRIX.md) in the repository.

## Runtime

| Component | Value |
|---|---|
| MaterialX SDK shipped with VRED 2027 | **1.39.4** |
| Library schema version | 1.39 (`adsklib` still declares 1.38) |
| Library location | `C:\Program Files\Autodesk\VREDPro-19.1\runtimeData\MaterialX\libraries` |
| Python bindings (PyMaterialX) | **Not shipped** - VredX writes `.mtlx` XML directly |
| VRED material class | `vrdMaterialXMaterial` (since VRED 2024) |
| Import path | `vrMaterialService.loadMaterials(["file.mtlx"])` or `vrdMaterialXMaterial.loadMaterial(path, index)` |
| Export path | **None** - VRED has no MaterialX export API; keep your source `.mtlx` files (VredX does this for you) |

## Supported shading models (BxDF graphs shipped with VRED)

| Shading model | MaterialX node | Notes |
|---|---|---|
| Autodesk Standard Surface | `standard_surface` v1.0.1 | Primary recommendation for PBR metal/rough |
| OpenPBR Surface | `open_pbr_surface` | 1.39 flagship model |
| glTF PBR | `gltf_pbr` | glTF interchange |
| USD Preview Surface | `UsdPreviewSurface` (+ `UsdUVTexture`, `UsdTransform2d`, `UsdPrimvarReader_*`) | Written by VRED's own USD exporter |
| Disney Principled | `disney_principled` | |
| RenderMan Lama | `LamaDiffuse`, `LamaConductor`, `LamaDielectric`, `LamaSSS`, `LamaSheen`, `LamaEmission`, `LamaTranslucent`, `LamaIridescence`, `LamaGeneralizedSchlick`, `LamaAdd`, `LamaMix`, `LamaLayer`, `LamaSurface` | Layerable BSDF stack |
| Unlit | `surface_unlit` | |
| Translation graphs | OpenPBR <-> Standard Surface, Standard Surface -> glTF/USD | Shipped in `bxdf/translation` |

## Node libraries (all parsed by VredX for the palette)

| Library | Contents | Shipped |
|---|---|---|
| `stdlib` | ~600 nodedefs: image/tiledimage, procedurals (noise2d/3d, fractal3d, cellnoise, worleynoise, unifiednoise2d/3d, ramps, checkerboard...), math, conditionals, channel ops (extract/separate/combine), color transforms, geometric lookups (`position`, `normal`, `texcoord`, `geompropvalue`...), compositing, convolution (blur, heighttonormal), `normalmap`, hex/lat-long images | Yes |
| `pbrlib` | BSDF/EDF/VDF building blocks (`oren_nayar_diffuse_bsdf`, `dielectric_bsdf`, `conductor_bsdf`, `generalized_schlick_bsdf`, `sheen_bsdf`, `thin_film_bsdf`, `subsurface_bsdf`, `uniform_edf`, `anisotropic_vdf`...), `surface`, `displacement`, `mix/layer/add/multiply` for BSDFs | Yes |
| `nprlib` | Non-photorealistic: `gooch_shade`, `viewdirection`, `facingratio` | Yes |
| `cmlib` | Color-space conversion nodegraphs | Yes |
| `adsklib` | Autodesk extras (`adsk_colorcorrect` etc.) | Only in the ATF import tree, **not** in the runtime library - avoid in hand-authored documents |
| `swizzle` | **Removed in 1.39** - use `extract` / `separate` / `combine` | n/a |

Note: shipping in the library means VRED's generators can compile the
node. Actual rendering support is exercised per-renderer (below).

## Renderer support

| Feature | OpenGL/Vulkan raster | Raytracing (CPU/GPU) |
|---|---|---|
| MaterialX materials in general | Yes (runtime GLSL codegen) | Yes (runtime codegen, OptiX/CPU) |
| `geompropvalue` scene-data lookups (vertex colors, AO, metadata, ray attributes) | Vulkan only | Yes |
| Thin film (`thin_film_bsdf`, `standard_surface` thin film) | No (raster preview won't show it) | Full GI raytracing only |
| Screen-space refractions | Vulkan only (`setUseScreenSpaceRefractions`) | n/a |
| **Displacement** | **Broken** (Autodesk staff, Jan 2026) | **Broken** |

## VRED-specific extensions

- **Scene data via `geompropvalue`** (docs: SceneData_GeomProps): camera/ray
  attributes (`ray:P`, `ray:D`, `ray:hitdist`, `FRAME`...), primitive
  attributes (`PRIMITIVE_ID`, `BARYCENTRICS`), vertex attributes
  (`vertex:normal`, `uv0`-`uv3`, `vertex:color`, `vertex:ambientocclusion`,
  `vertex:bakedlight`), and arbitrary VRED metadata keys (float/int).
- **Compilation types** (VRED 2027.1): `InstanceCompilation` (fast render,
  recompiles on edits) vs `ClassCompilation` (fast editing). VredX applies
  ClassCompilation by default.
- **Cutout transparency** (2027.1): binary opacity for foliage/grates.

## Known limitations and workarounds

| Limitation | Source | Workaround |
|---|---|---|
| Displacement does not render | Forum 13975031 (Autodesk staff) | Use normal mapping; VredX warns when displacement is used |
| No export of scene materials to `.mtlx` | API docs | VredX keeps the source `.mtlx` next to the material; `getPath()` recovers it |
| USD Preview Surface UV breaks on VRED->VRED USD reimport | Forum 12719939 | Switch material projection to Triplanar |
| Editing MaterialX gives up native VRED material controls | Forum 12127121 | BRDF common settings still available on `vrdMaterialXMaterial` |
| Runtime shader codegen makes shader caches less predictable | Forum 13774454 | Expect first-compile hitches; ClassCompilation reduces recompiles |
| No PyMaterialX in VRED's Python | Install inspection | VredX authors XML directly (no dependency) |

## VRED Python API surface (for reference)

```python
mat = vrMaterialService.createMaterial(name, vrMaterialTypes.MaterialType.MaterialX)
mat.loadMaterial("file.mtlx", 0)          # index into the document
mat.getPath()                             # source document path
mat.hasData(); mat.isDataValid()
mat.getActiveMaterialProperty(id); mat.setActiveMaterialProperty(id, value)
mat.getProperties().update(qobject)       # dynamic property introspection
mat.setCompilationType(vrdMaterialXMaterial.CompilationType.ClassCompilation)
mat.setUseCutoutTransparency(True)        # 2027.1
mat.setUseScreenSpaceRefractions(True)    # Vulkan only
```
