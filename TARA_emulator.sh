#!/usr/bin/env bash
# Usage: ./mem2hex.sh memory_dump.csv [out.hex]
# Converts the emulator's "address,hex,decimal" CSV into a Logisim v2.0 raw file
# of 16-bit words. The byte at the even address is the LOW byte of the word,
# so dump bytes 34 (addr 0), 19 (addr 1) -> hex word 1934.
in=$1
out=${2:-${in%.csv}_RAM.hex}

max=0
while IFS=, read -r addr hex _; do
  a=$((addr))
  mem[$a]=$((16#$hex))
  (( a > max )) && max=$a
done < <(tail -n +2 "$in" | tr -d '\r')

{
  echo "v2.0 raw"
  sep=""; n=0
  for (( a = 0; a <= max; a += 2 )); do
    printf '%s%02x%02x' "$sep" "${mem[a]:-0}" "${mem[a+1]:-0}"
    sep=" "; (( ++n % 12 == 0 )) && sep=$'\n'
  done
  echo
} > "$out"