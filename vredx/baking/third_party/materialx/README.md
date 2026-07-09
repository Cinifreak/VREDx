# ASWF MaterialX Runtime (bundled)

This folder holds the official ASWF MaterialX prebuilt release used by VredX
texture baking. It is **not modified** by VredX (Apache License 2.0).

## Release layout

Ship beside `VredX.py` in the download:

```
VredX/
  VredX.py
  vredx.zip
  baking_runtime/
    materialx/          ← extract ASWF bundle here
```

Download **MaterialX 1.39.5** for Windows (Python 3.13) from
[MaterialX releases](https://github.com/AcademySoftwareFoundation/MaterialX/releases)
into `baking_runtime/materialx/`.

## End-user install

Move `baking_runtime` to:

```
Documents/Autodesk/VredX/baking_runtime/
```

VRED must not load the ASWF Python tree from ScriptPlugins (it scans loose
`.py` files). Until the runtime is moved, VredX works normally but hides all
baking UI.

## Expected layout

```
materialx/
  bin/              native DLLs and MaterialXView
  python/           PyMaterialX cp313 extension modules
  python313/        embeddable CPython 3.13 (runs the baker subprocess)
  libraries/        MaterialX nodedef libraries
```

## License

See ../NOTICE.txt and ../LICENSE-ASWF-MaterialX.txt
