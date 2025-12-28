#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build do site estático para GitHub Pages.

Entrada:
  - Coloque arquivos .ifc dentro da pasta ./ifc/

Saída:
  - ./site/ (artefato publicado no GitHub Pages)
    - index.html (lista de modelos)
    - models.json
    - <slug>/index.html (viewer)
    - <slug>/model.glb
    - <slug>/metadata.json

Requisitos:
  - IfcConvert (binário) no PATH ou fornecido via --ifcconvert
  - ifcopenshell (pip) para extração de metadados
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    import ifcopenshell  # type: ignore
except Exception as e:
    ifcopenshell = None  # type: ignore


def slugify(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9\-_]+", "-", name, flags=re.IGNORECASE)
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "modelo"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def find_ifcconvert(user_path: str | None) -> str:
    # 1) explicit
    if user_path:
        p = Path(user_path)
        if p.exists():
            return str(p)
    # 2) env var
    env = os.environ.get("IFCCONVERT_BIN")
    if env and Path(env).exists():
        return env
    # 3) PATH
    from shutil import which
    for cand in ["IfcConvert", "ifcconvert", "IfcConvert.exe", "ifcconvert.exe"]:
        w = which(cand)
        if w:
            return w
    raise FileNotFoundError("IfcConvert não encontrado. Defina --ifcconvert ou IFCCONVERT_BIN.")


def to_jsonable(v: Any) -> Any:
    # Converte valores do ifcopenshell (e tipos estranhos) para JSON
    try:
        if ifcopenshell is not None and isinstance(v, ifcopenshell.entity_instance):  # type: ignore
            # Ex: IfcLabel('ABC'), IfcLengthMeasure(1.23) etc
            # Preferimos string curta
            try:
                return str(v)
            except Exception:
                return {"id": getattr(v, "id", lambda: None)()}
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        if isinstance(v, dict):
            return {str(k): to_jsonable(val) for k, val in v.items()}
        if isinstance(v, (list, tuple, set)):
            return [to_jsonable(x) for x in v]
        # numpy / decimals
        if hasattr(v, "item") and callable(getattr(v, "item")):
            return to_jsonable(v.item())
    except Exception:
        pass
    return str(v)


def get_storey_name(elem: Any) -> str | None:
    """Tenta descobrir o IfcBuildingStorey que contém o elemento."""
    # IFC2X3/IFC4: IfcProduct.ContainedInStructure -> IfcRelContainedInSpatialStructure.RelatingStructure
    try:
        rels = getattr(elem, "ContainedInStructure", None)
        if rels:
            for rel in rels:
                struct = getattr(rel, "RelatingStructure", None)
                if struct and hasattr(struct, "is_a") and struct.is_a("IfcBuildingStorey"):
                    return getattr(struct, "Name", None) or getattr(struct, "LongName", None)
    except Exception:
        pass
    return None


def extract_metadata(ifc_path: Path) -> Dict[str, Any]:
    if ifcopenshell is None:
        print("[WARN] ifcopenshell não está instalado. metadata.json será vazio.")
        return {}

    model = ifcopenshell.open(str(ifc_path))  # type: ignore
    # Import opcional de utilidades
    get_psets = None
    try:
        from ifcopenshell.util.element import get_psets as _get_psets  # type: ignore
        get_psets = _get_psets
    except Exception:
        pass

    out: Dict[str, Any] = {}

    # Foco em elementos físicos (IfcProduct) exceto aberturas
    for elem in model.by_type("IfcProduct"):
        try:
            if elem.is_a("IfcOpeningElement"):
                continue
            guid = getattr(elem, "GlobalId", None)
            if not guid:
                continue

            item: Dict[str, Any] = {
                "type": elem.is_a(),
                "name": getattr(elem, "Name", None),
                "tag": getattr(elem, "Tag", None),
                "storey": get_storey_name(elem),
            }

            if get_psets:
                try:
                    item["psets"] = to_jsonable(get_psets(elem, include_inherited=True))  # type: ignore
                except Exception:
                    item["psets"] = {}
            out[str(guid)] = item
        except Exception:
            # Nunca derrubar o build por causa de um elemento estranho
            continue

    return out


def convert_ifc_to_glb(ifcconvert_bin: str, ifc_path: Path, glb_path: Path) -> None:
    glb_path.parent.mkdir(parents=True, exist_ok=True)

    # Preferimos GUID no nome do nó (facilita seleção por GUID no viewer)
    # Nota: --use-element-guids é documentado para alguns formatos e, na prática,
    # costuma funcionar também na exportação glTF/GLB em muitos casos.
    base_cmd = [ifcconvert_bin, "--center-model-geometry", "--use-element-guids", str(ifc_path), str(glb_path)]

    try:
        run(base_cmd)
    except subprocess.CalledProcessError:
        print("[WARN] Falhou com --use-element-guids. Tentando sem essa opção...")
        run([ifcconvert_bin, "--center-model-geometry", str(ifc_path), str(glb_path)])


@dataclass
class ModelEntry:
    name: str
    slug: str
    updated: str


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ifc_dir", default="ifc", help="Pasta com IFCs de entrada")
    ap.add_argument("--site_dir", default="site", help="Pasta de saída publicada no Pages")
    ap.add_argument("--viewer_template", default="viewer/index.html", help="HTML do viewer")
    ap.add_argument("--root_template", default="viewer/root_index.html", help="HTML do índice" )
    ap.add_argument("--ifcconvert", default=None, help="Caminho do IfcConvert")

    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    ifc_dir = repo_root / args.ifc_dir
    site_dir = repo_root / args.site_dir
    viewer_template = repo_root / args.viewer_template
    root_template = repo_root / args.root_template

    if not viewer_template.exists():
        raise FileNotFoundError(f"Viewer template não encontrado: {viewer_template}")
    if not root_template.exists():
        raise FileNotFoundError(f"Root template não encontrado: {root_template}")

    ifcconvert_bin = find_ifcconvert(args.ifcconvert)

    if not ifc_dir.exists():
        print(f"[INFO] Pasta {ifc_dir} não existe. Nada a fazer.")
        return

    # Limpa site/
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    models: list[ModelEntry] = []

    for ifc_path in sorted(ifc_dir.glob("*.ifc")):
        name = ifc_path.stem
        slug = slugify(name)

        out_dir = site_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        glb_path = out_dir / "model.glb"
        meta_path = out_dir / "metadata.json"
        index_path = out_dir / "index.html"

        print(f"\n=== {name} -> {slug} ===")
        convert_ifc_to_glb(ifcconvert_bin, ifc_path, glb_path)

        print("[INFO] Extraindo metadados...")
        metadata = extract_metadata(ifc_path)
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

        # Copia viewer
        shutil.copy2(viewer_template, index_path)

        updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        models.append(ModelEntry(name=name, slug=slug, updated=updated))

    # models.json
    models_json = [{"name": m.name, "path": m.slug, "updated": m.updated} for m in models]
    (site_dir / "models.json").write_text(json.dumps(models_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # index.html (root)
    shutil.copy2(root_template, site_dir / "index.html")

    print("\n[OK] Site gerado em:", site_dir)


if __name__ == "__main__":
    main()
