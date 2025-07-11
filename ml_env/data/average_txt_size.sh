#!/bin/bash

# Get all .txt files in the current directory
files=(*.txt)

# Handle the case where no .txt files exist
if [ ${#files[@]} -eq 0 ]; then
  echo "No .txt files found."
  exit 1
fi

# Sum file sizes
total_size=0
count=0
max_size=0
largest_file=""

for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    size=$(stat -c%s "$file")
    total_size=$((total_size + size))
    count=$((count + 1))
    if [ "$size" -gt "$max_size" ]; then
      max_size=$size
      largest_file=$file
    fi
  fi
done

# Calculate average
average_size=$((total_size / count))

echo "Average size of $count .txt files: $average_size bytes"
echo "Largest file: $largest_file ($max_size bytes)"

