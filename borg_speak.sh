#!/bin/bash

PHRASE="$*"
OUTFILE="borg_output.wav"
TMPDIR="/tmp/borg_voices"
SPEED=130

mkdir -p "$TMPDIR"

# Step 1: Generate a single base voice file
espeak -v en+m3 -p 35 -s "$SPEED" "$PHRASE" -w "$TMPDIR/base.wav"

# Step 2: Create 6 pitch-shifted variants (same timing, different tone)
for i in {1..6}; do
    SHIFT=$(( (RANDOM % 600) - 300 )) # Pitch shift in cents
    sox "$TMPDIR/base.wav" "$TMPDIR/voice$i.wav" pitch "$SHIFT"
done

# Step 3: Mix all variants into one creepy collective
sox -m "$TMPDIR"/voice{1..6}.wav "$TMPDIR/mixed.wav"

# Step 4: Add chorus effect for extra hive flavor
sox "$TMPDIR/mixed.wav" "$OUTFILE" chorus 0.6 0.9 55 0.4 0.25 2 -t

# Step 5: Play the result silently (suppress ALSA complaints)
paplay "$OUTFILE"
#aplay "$OUTFILE" >/dev/null 2>&1 #for normal speakers

