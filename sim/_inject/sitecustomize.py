"""Loaded by the ManiSkill worker via PYTHONPATH. Patches the Ditto task when it is imported.

It must not import ditto eagerly: ditto.base needs the MolmoAct2 source root, which the
worker adds to sys.path only after startup. A meta-path hook waits for the import instead.
"""
import os
import sys

if os.environ.get("GAPHUNTER_PARAMS"):
    import importlib.abc
    import importlib.machinery

    _TARGET = "ditto.tasks.geometry_tasks"

    class _GapHunterHook(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != _TARGET:
                return None
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(name, path)
            if spec is None or spec.loader is None:
                return spec
            exec_module = spec.loader.exec_module

            def exec_and_patch(module):
                exec_module(module)
                import importlib.util
                path = os.path.join(os.environ["GAPHUNTER_ROOT"], "sim", "task_override.py")
                override_spec = importlib.util.spec_from_file_location("gaphunter_task_override", path)
                override = importlib.util.module_from_spec(override_spec)
                override_spec.loader.exec_module(override)
                override.patch()
                print(f"[gaphunter] offsets {os.environ['GAPHUNTER_PARAMS']} patched into {_TARGET}",
                      file=sys.stderr, flush=True)

            spec.loader.exec_module = exec_and_patch
            return spec

    sys.meta_path.insert(0, _GapHunterHook())
