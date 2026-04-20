#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.frontend.yml"
SERVICE_NAME="${FRONTEND_BUILDER_SERVICE:-frontend-builder}"
RELEASE_ROOT="${FRONTEND_RELEASE_ROOT:-$ROOT_DIR/frontend-dist}"
RELEASE_VERSION="${FRONTEND_RELEASE_VERSION:-$(date -u +%Y%m%d-%H%M%S)}"
RELEASES_DIR="$RELEASE_ROOT/releases"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_VERSION"
TMP_DIR="$RELEASES_DIR/.tmp-$RELEASE_VERSION"

mkdir -p "$RELEASES_DIR"

if [ -e "$RELEASE_DIR" ] || [ -e "$TMP_DIR" ]; then
    echo "发布版本已存在，请更换 FRONTEND_RELEASE_VERSION: $RELEASE_VERSION" >&2
    exit 1
fi

docker compose -f "$COMPOSE_FILE" build "$SERVICE_NAME"

trap 'docker compose -f "$COMPOSE_FILE" rm -f -s -v "$SERVICE_NAME" >/dev/null 2>&1 || true' EXIT

docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint /bin/sh \
    -e RELEASE_ROOT=/out \
    -e RELEASE_VERSION="$RELEASE_VERSION" \
    "$SERVICE_NAME" \
    -lc '
        set -eu
        target="$RELEASE_ROOT/releases/$RELEASE_VERSION"
        temp="$RELEASE_ROOT/releases/.tmp-$RELEASE_VERSION"

        test ! -e "$target"
        test ! -e "$temp"

        mkdir -p "$temp"
        cp -a /app/dist/. "$temp"/
        test -f "$temp/index.html"

        mv "$temp" "$target"
        ln -sfn "releases/$RELEASE_VERSION" "$RELEASE_ROOT/current"
    '

echo "前端静态资源已发布: $RELEASE_VERSION"
echo "当前发布指向: $RELEASE_ROOT/current"
