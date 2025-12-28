# IFC Viewer (GitHub Pages)

Este repositório publica um viewer Web (Three.js) no **GitHub Pages** e gera automaticamente:
- `model.glb` (a partir do IFC)
- `metadata.json` (propriedades / psets básicos via ifcopenshell)
- um link por modelo: `https://SEUUSUARIO.github.io/SEUREPO/<nome-do-modelo>/`

## Como usar (rápido)

1. Envie um arquivo `.ifc` para a pasta `ifc/` (pelo GitHub ou git).
2. Aguarde o workflow **Build and Deploy IFC Viewer** terminar (aba *Actions*).
3. Abra o Pages:
   - `https://SEUUSUARIO.github.io/SEUREPO/` (lista)
   - `https://SEUUSUARIO.github.io/SEUREPO/<modelo>/` (viewer)

## Observações importantes

- GitHub Pages é público. Para arquivos sensíveis, use repositório/Pages privado (depende do seu plano) ou outro host com autenticação.
- Upload pelo navegador tem limite menor. Se o `.ifc` ou `.glb` ficar grande, use git via desktop ou Git LFS.

