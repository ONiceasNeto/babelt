#!/usr/bin/env bash
# Converte o modelo NMT e empacota o artefato que o babelt baixa.
#
# **Este script é para quem publica, não para o usuário.** É aqui que
# `transformers` e `torch` são necessários — cerca de 2 GB —, e é justamente
# para que o usuário não precise deles que a conversão acontece uma vez, aqui,
# e não em cada instalação.
#
#     python3 -m venv .venv
#     .venv/bin/pip install -e '.[convert]'      # -e '.', do repositório
#     ./scripts/build-model.sh
#
# Note o `-e '.'`: `pip install 'babelt[convert]'` iria ao PyPI, onde o pacote
# ainda não existe.
#
# No fim imprime a URL sugerida e o SHA-256 para colar em babelt/model.py.
set -euo pipefail

MODEL_ID=${MODEL_ID:-Helsinki-NLP/opus-mt-tc-big-en-pt}
OUT_DIR=${OUT_DIR:-dist}
NAME=${NAME:-babelt-model-en-pt-int8}

cd "$(dirname "$0")/.."
mkdir -p "$OUT_DIR"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# O interpretador: o do venv, se houver, senão python3. Nunca `python` — em
# Debian, Ubuntu e derivados esse nome não existe, e o script morria na linha
# do converter com "command not found".
if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
else
  PYTHON=${PYTHON:-python3}
fi

# O converter vem do pacote `transformers`, que só está no extra `convert`.
# Falhar aqui, antes de qualquer download, com a linha exata que resolve.
if [ -x .venv/bin/ct2-transformers-converter ]; then
  converter=(.venv/bin/ct2-transformers-converter)
elif command -v ct2-transformers-converter > /dev/null 2>&1; then
  converter=(ct2-transformers-converter)
elif "$PYTHON" -c 'import transformers' 2> /dev/null; then
  converter=("$PYTHON" -m ctranslate2.converters.transformers)
else
  cat >&2 <<'EOF'
erro: ct2-transformers-converter não encontrado.

Ele vem com o extra `convert`, que é o único lugar onde `transformers` e
`torch` são necessários. No diretório do repositório:

    python3 -m venv .venv
    .venv/bin/pip install -e '.[convert]'

`pip install 'babelt[convert]'` não serve: iria ao PyPI, onde o pacote ainda
não está publicado.
EOF
  exit 1
fi

echo "convertendo $MODEL_ID para CTranslate2 int8 com $PYTHON…" >&2

"${converter[@]}" \
  --model "$MODEL_ID" \
  --output_dir "$work/en-pt" \
  --quantization int8 \
  --copy_files source.spm target.spm tokenizer_config.json

# Confere antes de empacotar: um artefato incompleto publicado é pior que uma
# conversão que falhou, porque falha na máquina de quem baixou.
for required in model.bin source.spm target.spm; do
  [ -s "$work/en-pt/$required" ] || { echo "erro: $required ausente ou vazio" >&2; exit 1; }
done
ls "$work/en-pt" | grep -q '^shared_vocabulary\.' || {
  echo "erro: vocabulário compartilhado ausente" >&2; exit 1; }

# Proveniência dentro do artefato: quem baixa precisa poder saber de onde veio
# e sob que licença. `babelt doctor` lê este arquivo.
cat > "$work/en-pt/meta.json" <<EOF
{
  "model_id": "$MODEL_ID",
  "quantization": "int8",
  "converted": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "converter": "ctranslate2",
  "license": "CC-BY-4.0",
  "attribution": "Helsinki-NLP / Language Technology Research Group, University of Helsinki"
}
EOF

cp LICENSE "$work/en-pt/LICENSE-babelt" 2>/dev/null || true
cat > "$work/en-pt/NOTICE" <<EOF
Este artefato contém o modelo $MODEL_ID, do grupo Language Technology Research
Group da Universidade de Helsinque (Helsinki-NLP), convertido para o formato
CTranslate2 com quantização int8. O modelo é distribuído sob CC-BY-4.0; a
conversão não altera a licença nem a autoria.

O babelt, que baixa e usa este artefato, é distribuído sob MIT.
EOF

archive="$OUT_DIR/$NAME.tar.gz"
tar -czf "$archive" -C "$work" en-pt

sha=$(sha256sum "$archive" | cut -d' ' -f1)
size=$(du -h "$archive" | cut -f1)

cat >&2 <<EOF

artefato: $archive ($size)

Cole em babelt/model.py:

    MODEL_URL: Final = "https://…/$NAME.tar.gz"
    MODEL_SHA256: Final = "$sha"
EOF
