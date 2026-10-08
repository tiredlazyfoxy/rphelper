#!/usr/bin/env bash
# RPHelper deploy script — staged into $DOCKER_STORE/rphelper by build.sh, run on the server.
# Usage: deploy.sh [--images|--config|--all] [--no-restart]   (default: --all, restart on)
# Requires: $DOCKER_STORE (non-empty; trailing slash tolerated) and an existing
# $DOCKER_STORE/rphelper; when restarting, a .env next to this script (never created here).
# Loads rphelper-latest.7z (7z x -so | docker load), copies the store docker-compose.yml next
# to this script, mkdir -p data, then docker compose up -d + docker image prune -f; always
# finishes with docker compose ps.

set -euo pipefail

usage() { echo "usage: deploy.sh [--images|--config|--all] [--no-restart]" >&2; exit 1; }
die() { echo "deploy.sh: $*" >&2; exit 1; }

mode="all"
restart=1
for arg in "$@"; do
    case "$arg" in
        --images) mode="images" ;;
        --config) mode="config" ;;
        --all) mode="all" ;;
        --no-restart) restart=0 ;;
        *) usage ;;
    esac
done

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

store_base="${DOCKER_STORE:-}"
[[ -n "$store_base" ]] || die "DOCKER_STORE is not set (or empty); it must name the docker store directory"
while [[ "$store_base" == */ && "$store_base" != / ]]; do
    store_base="${store_base%/}"
done
store="${store_base%/}/rphelper"
[[ -d "$store" ]] || die "store directory $store does not exist (run build.sh first)"

archive="$store/rphelper-latest.7z"
compose="$store/docker-compose.yml"

if [[ "$restart" -eq 1 && ! -f "$here/.env" ]]; then
    die "missing $here/.env (create it from .env.example; it is never created here), or pass --no-restart"
fi
if [[ "$mode" != "config" && ! -f "$archive" ]]; then
    die "missing image archive $archive"
fi
if [[ "$mode" != "images" && ! -f "$compose" ]]; then
    die "missing compose file $compose"
fi

if [[ "$mode" != "config" ]]; then
    echo "Loading images from $archive"
    7z x -so "$archive" | docker load
fi

if [[ "$mode" != "images" ]]; then
    echo "Copying $compose -> $here/docker-compose.yml"
    cp "$compose" "$here/docker-compose.yml"
fi

mkdir -p "$here/data"
cd "$here"

if [[ "$restart" -eq 1 ]]; then
    docker compose up -d
    docker image prune -f
fi

docker compose ps
