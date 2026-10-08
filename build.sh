#!/usr/bin/env bash
# RPHelper host-side build-and-stage script.
# Usage: build.sh            (no arguments)
# Requires: $DOCKER_STORE (non-empty; trailing slash tolerated); HEAD tagged with exactly
# one vX.Y.Z tag. Builds iezious/rphelper:latest + :<X.Y.Z> from this script's directory,
# packs both into $DOCKER_STORE/rphelper/rphelper-latest.7z (via a temp archive + mv), and
# stages docker-compose.prod.yml (as docker-compose.yml) and deploy.sh next to it.

set -euo pipefail

image="iezious/rphelper"

die() { echo "build.sh: $*" >&2; exit 1; }

if [[ $# -ne 0 ]]; then
    echo "usage: build.sh   (takes no arguments; set DOCKER_STORE, tag HEAD vX.Y.Z)" >&2
    exit 1
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

store_base="${DOCKER_STORE:-}"
[[ -n "$store_base" ]] || die "DOCKER_STORE is not set (or empty); it must name the docker store directory"
while [[ "$store_base" == */ && "$store_base" != / ]]; do
    store_base="${store_base%/}"
done
store="${store_base%/}/rphelper"

for f in docker-compose.prod.yml deploy.sh; do
    [[ -f "$root/$f" ]] || die "missing $root/$f"
done

if ! tags="$(git -C "$root" tag --points-at HEAD)"; then
    die "cannot list git tags on HEAD; HEAD must carry exactly one vX.Y.Z tag (e.g. v0.0.1)"
fi
matches=()
while IFS= read -r tag; do
    if [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        matches+=("$tag")
    fi
done <<< "$tags"
if [[ ${#matches[@]} -eq 0 ]]; then
    die "HEAD has no vX.Y.Z version tag (e.g. v0.0.1); tag it first: git tag v0.0.1"
fi
if [[ ${#matches[@]} -gt 1 ]]; then
    die "HEAD has several vX.Y.Z version tags (${matches[*]}); expected exactly one"
fi
version="${matches[0]#v}"

echo "Version: $version"
echo "Store:   $store"

docker build -t "$image:latest" -t "$image:$version" "$root"

mkdir -p "$store"

tmp=""
cleanup() { if [[ -n "$tmp" ]]; then rm -f "$tmp"; fi; }
trap cleanup EXIT

tmp="$(mktemp -u "$store/.rphelper-latest.XXXXXX.7z")"
docker save "$image:latest" "$image:$version" | 7z a -t7z -bd -sirphelper.tar "$tmp"
mv -f "$tmp" "$store/rphelper-latest.7z"
tmp=""

cp "$root/docker-compose.prod.yml" "$store/docker-compose.yml"
cp "$root/deploy.sh" "$store/deploy.sh"
chmod +x "$store/deploy.sh"

echo "Staged in $store:"
echo "  rphelper-latest.7z  ($image:latest + $image:$version)"
echo "  docker-compose.yml  (from docker-compose.prod.yml)"
echo "  deploy.sh"
