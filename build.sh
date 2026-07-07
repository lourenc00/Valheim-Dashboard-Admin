#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/out"
SRV="/home/vhserver/serverfiles"
MCS="mcs"

UNITY_BCL="$SRV/valheim_server_Data/Managed"
BEPINEX="$SRV/BepInEx/core"

REFERENCIAS="-nostdlib"
for asm in \
  "$UNITY_BCL/mscorlib.dll" \
  "$UNITY_BCL/System.dll" \
  "$UNITY_BCL/System.Core.dll" \
  "$UNITY_BCL/netstandard.dll" \
  "$UNITY_BCL/System.Net.dll" \
  "$UNITY_BCL/System.Net.Http.dll" \
  "$UNITY_BCL/UnityEngine.dll" \
  "$UNITY_BCL/UnityEngine.CoreModule.dll" \
  "$UNITY_BCL/assembly_valheim.dll" \
  "$BEPINEX/BepInEx.dll" \
  "$BEPINEX/0Harmony.dll"
do
  if [ -f "$asm" ]; then
    REFERENCIAS="$REFERENCIAS -r:$asm"
  fi
done

mkdir -p "$OUT"
$MCS -sdk:4 -target:library -out:"$OUT/AdminPowers.dll" \
  $REFERENCIAS \
  "$DIR/Plugin.cs"

if [ $? -eq 0 ]; then
  echo "=== Build OK: $OUT/AdminPowers.dll ==="
  ls -la "$OUT/AdminPowers.dll"
else
  echo "=== BUILD FAILED ==="
  exit 1
fi
