#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
out="evidence/$run_id"
mkdir -p "$out"
container_name=""
check_name="setup"

cleanup() {
    code=$?
    if [[ -n "$container_name" ]]; then
        docker logs "$container_name" > "$out/$check_name-container.log" 2>&1 || true
        docker stop -t 5 "$container_name" >/dev/null 2>&1 || true
    fi
    if [[ "$code" -ne 0 ]]; then
        printf '| %s | See test log | Check stopped with an error | FAIL |\n' "$check_name" >> "$out/results.md"
        printf '\nChecks stopped. Logs: %s\n' "$out"
    fi
}
trap cleanup EXIT

printf '# Acceptance checks\n\nRun: %s\n\n| Check | Expected | Actual | Result |\n|---|---|---|---|\n' "$run_id" > "$out/results.md"
docker build -t seal-log:lab . 2>&1 | tee "$out/build.txt"
image_id=$(docker image inspect seal-log:lab --format '{{.Id}}')
docker image inspect "$image_id" > "$out/image.json"
docker version > "$out/docker-version.txt"
sha256sum app.py schema.sql Dockerfile requirements.txt > "$out/source-sha256.txt"

for check_name in normal isolation limit; do
    container_name="seal-log-check-$run_id-$check_name"
    volume_name="$container_name-data"
    docker volume create "$volume_name" >/dev/null
    printf '%s %s\n' "$check_name" "$volume_name" >> "$out/volumes.txt"
    docker run --rm \
        --mount "type=volume,source=$volume_name,target=/data" \
        "$image_id" flask --app app init-db > "$out/$check_name-init.txt" 2>&1
    docker run -d --rm --name "$container_name" \
        --mount "type=volume,source=$volume_name,target=/data" \
        "$image_id" >/dev/null
    docker exec -i "$container_name" python -u - "$check_name" \
        < tests/acceptance.py 2>&1 | tee "$out/$check_name.txt"
    docker logs "$container_name" > "$out/$check_name-container.log" 2>&1
    docker stop -t 5 "$container_name" >/dev/null
    container_name=""
    sed -n 's/^RESULT: //p' "$out/$check_name.txt" >> "$out/results.md"
done

printf '\nAll three checks passed. Evidence: %s\n\n' "$out"
cat "$out/results.md"
