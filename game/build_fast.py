"""Optional speed-up: compile the hot loops of scripts/physics.py (scripts/_fast.pyx).

    pip install cython setuptools        (one time)
    python build_fast.py                 (run from this folder; re-run after editing _fast.pyx)

Needs a C compiler: Windows -> "Microsoft C++ Build Tools" (Desktop development with C++),
Linux -> gcc, macOS -> Xcode command line tools.

This produces scripts/_fast.<platform>.pyd/.so next to physics.py. The game picks it up by
itself; delete that file and it silently goes back to the pure-Python code. Nothing else
changes, so the game still runs unbuilt.

    python build_fast.py --all           also compile scripts/physics.py itself (a bit faster
                                         again, but a stale build will hide edits to physics.py:
                                         re-run this, or delete scripts/physics.*.pyd/.so)
"""
import os
import sys

from setuptools import Extension, setup
from Cython.Build import cythonize

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
flags = ["/O2"] if sys.platform == "win32" else ["-O3"]

modules = [Extension("scripts._fast", ["scripts/_fast.pyx"], extra_compile_args=flags)]
if "--all" in sys.argv:
    sys.argv.remove("--all")
    modules.append(Extension("scripts.physics", ["scripts/physics.py"], extra_compile_args=flags))

setup(
    name="pixel_abyss_fast",
    ext_modules=cythonize(
        modules,
        compiler_directives={"language_level": 3, "boundscheck": False, "wraparound": False, "cdivision": True},
    ),
    script_args=["build_ext", "--inplace", "-q"],
)
print("built:", ", ".join(m.name for m in modules))
