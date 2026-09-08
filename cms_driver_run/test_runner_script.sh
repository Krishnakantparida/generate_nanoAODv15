#!/bin/bash

# Test runner that submits Condor jobs for each chunk list in Test_datasets.
# Files matching "singlemu*" are treated as data and use the data JDL.
# All other files are treated as MC and use the MC JDL.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TEST_DIR="$SCRIPT_DIR/Test_datasets"

# Ensure the driver scripts are executable
chmod +x "$SCRIPT_DIR/run_cmsdriver_mc.sh" "$SCRIPT_DIR/run_cmsdriver_data.sh"

if [[ -z "${X509_USER_PROXY:-}" ]]; then
    echo "Warning: X509_USER_PROXY is not set; Condor may not access CMS storage." >&2
fi

# Iterate over each chunk list file
for chunk_file in "$TEST_DIR"/*; do
    filename=$(basename "$chunk_file")
    # Derive a simple SampleName without extensions and path components
    # For data files (singlemu*), use the filename without extension as SampleName
    # For MC files, strip the leading "miniAODSIM_chunk_" and any trailing suffixes.
    # Determine whether the chunk file is for data or MC based on its prefix.
    if [[ "$filename" == miniAOD_* ]]; then
        # Data chunk: strip the "miniAOD_chunk_" prefix and any extension.
        SAMPLE_NAME="${filename#miniAOD_chunk_}"
        SAMPLE_NAME="${SAMPLE_NAME%.*}"   # remove trailing .txt if present
        JDL="cms_nanoAODv15_data.jdl"
    elif [[ "$filename" == miniAODSIM_* ]]; then
        # MC chunk: strip the "miniAODSIM_chunk_" prefix and any extension.
        SAMPLE_NAME="${filename#miniAODSIM_chunk_}"
        SAMPLE_NAME="${SAMPLE_NAME%.*}"   # remove trailing .txt if present
        JDL="cms_nanoAODv15_mc.jdl"
    else
        echo "Skipping unrecognized chunk file: $filename"
        continue
    fi

    # Submit the job with explicit SampleName and InputFile variables.
    # Condor allows overriding variables on the command line via -append.
    echo "Submitting $filename as $SAMPLE_NAME using $JDL"
    condor_submit "$JDL" -append "SampleName=$SAMPLE_NAME" -append "InputFile=$(basename "$chunk_file")"
done

# Show queue status after submissions
condor_q
