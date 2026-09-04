#!/bin/bash

# HTCondor Job Script for CMS Data NanoAOD Production
# CMSSW Setup and cmsDriver.py execution for Data
# Output files are stored in EOS space
# CMSSW environment is set up from batch space (not AFS)

set -euo pipefail  # Exit on any error

JOBID="${1:?Usage: run_cmsdriver_data.sh JOBID [YAML_HEADER_SAMPLE] [INPUT_LIST]}"
SAMPLE_NAME="${2:-${SAMPLE_NAME:-unclassified}}"
SAMPLE_DIR=$(printf "%s" "$SAMPLE_NAME" | sed 's/[^A-Za-z0-9_.-]/_/g')
if [ "$SAMPLE_DIR" = "unclassified" ]; then
    INPUT_LIST="${3:-miniAOD_chunk_${JOBID}.txt}"
else
    INPUT_LIST="${3:-miniAOD_chunk_${SAMPLE_DIR}_${JOBID}.txt}"
fi
OUTPUT_FILE="NANOAOD_${SAMPLE_DIR}_${JOBID}.root"
CFG_FILE="Data24_NanoAODv15_${SAMPLE_DIR}_${JOBID}.py"
SUBMIT_DIR="$PWD"
ANALYSIS_DIR="${SUBMIT_DIR}/MyAnalysis"
CUSTOMIZE_FILE="${SUBMIT_DIR}/cmsskim_customize.py"

if [ ! -d "$ANALYSIS_DIR" ] && [ -d "${SUBMIT_DIR}/../MyAnalysis" ]; then
    ANALYSIS_DIR="${SUBMIT_DIR}/../MyAnalysis"
fi

if [ ! -f "$CUSTOMIZE_FILE" ] && [ -f "${SUBMIT_DIR}/../cmsskim_customize.py" ]; then
    CUSTOMIZE_FILE="${SUBMIT_DIR}/../cmsskim_customize.py"
fi

echo "=========================================="
echo "Data NanoAOD Production Job"
echo "Host: $(hostname)"
echo "Start time: $(date)"
echo "=========================================="
echo "Starting NanoAOD job ${JOBID}"
echo "YAML header sample: ${SAMPLE_NAME}"
echo "Current directory: $(pwd)"
echo ""

# ============================================
# Setup CMSSW environment from batch space
# ============================================
# CMSSW will be downloaded/set up in the batch job directory
export CMSSW_VERSION="CMSSW_15_0_15_patch4"
export SCRAM_ARCH="el9_amd64_gcc12"

# Create CMSSW setup in batch space (local work directory)
export BATCH_CMSSW_BASE="$PWD/$CMSSW_VERSION"
export LOCAL_WORK_DIR="$PWD/work_data_$$"

echo "CMSSW Version: $CMSSW_VERSION"
echo "SCRAM Architecture: $SCRAM_ARCH"
echo "BATCH CMSSW Base: $BATCH_CMSSW_BASE"
echo "Local Work Dir: $LOCAL_WORK_DIR"
echo ""

# ============================================
# Setup CMS environment
# ============================================
echo "Setting up CMS environment..."
source /cvmfs/cms.cern.ch/cmsset_default.sh
export SCRAM_ARCH=$SCRAM_ARCH

# Check if CMSSW already exists in batch space, if not create it
if [ ! -d "$BATCH_CMSSW_BASE" ]; then
    echo "Creating CMSSW release in batch space..."
    cd $PWD
    scramv1 project CMSSW $CMSSW_VERSION
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create CMSSW release"
        exit 1
    fi
    echo "✓ CMSSW release created successfully"
else
    echo "✓ CMSSW release already exists at $BATCH_CMSSW_BASE"
fi

cd $BATCH_CMSSW_BASE
eval `scramv1 runtime -sh`

echo "CMSSW Base: $CMSSW_BASE"
echo "CMSSW_VERSION: $CMSSW_VERSION"
echo ""

# ============================================
# Build local analysis plugins
# ============================================
if [ -d "$ANALYSIS_DIR" ]; then
    echo "Installing local MyAnalysis plugins into CMSSW src..."
    mkdir -p "$CMSSW_BASE/src"
    cp -R "$ANALYSIS_DIR" "$CMSSW_BASE/src/"

    echo "Building local plugins..."
    cd "$CMSSW_BASE/src"
    scram b -j8
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to build local MyAnalysis plugins"
        exit 1
    fi
    echo "Local plugins built successfully"
    cd "$BATCH_CMSSW_BASE"
else
    echo "ERROR: Local plugin package MyAnalysis was not transferred with the job"
    exit 1
fi

# Create work directory
mkdir -p $LOCAL_WORK_DIR
cd $LOCAL_WORK_DIR

# ============================================
# Setup EOS storage paths
# ============================================
export EOS_USERNAME=$(whoami)
EOS_ENDPOINT="root://cmseos.fnal.gov"
export EOS_OUTPUT_BASE="/eos/uscms/store/group/lpcjm/${EOS_USERNAME}/cms_nanoaod/data/${SAMPLE_DIR}"

echo "Checking CMSLPC EOS access..."

if ! xrdfs "${EOS_ENDPOINT}" stat "${EOS_OUTPUT_BASE}" >/dev/null 2>&1; then
    echo "Creating CMSLPC EOS destination:"
    echo " ${EOS_ENDPOINT}/${EOS_OUTPUT_BASE}"
    xrdfs "${EOS_ENDPOINT}" mkdir -p "${EOS_OUTPUT_BASE}"
fi

if ! xrdfs "${EOS_ENDPOINT}" stat "${EOS_OUTPUT_BASE}"; then
    echo "ERROR: CMSLPC EOS destination is not accessible:"
    echo " ${EOS_ENDPOINT}/${EOS_OUTPUT_BASE}"
    echo "Check the destination path, group permissions, and proxy."
    exit 1
fi

echo "CMSLPC EOS destination is accessible."

echo "EOS Output Base: $EOS_OUTPUT_BASE"
echo "Local Work Dir: $LOCAL_WORK_DIR"
echo ""


# Create EOS directories if they don't exist
#echo "Creating EOS directory structure..."
#mkdir -p $EOS_OUTPUT_BASE
#eos mkdir -p $EOS_OUTPUT_BASE 2>/dev/null || true

echo "EOS directory ready: $EOS_OUTPUT_BASE"
echo ""

# ============================================
# Data NanoAOD Production
# ============================================
echo "Generating Data NanoAOD config file..."
# Copy input list to work directory
cp "${SUBMIT_DIR}/${INPUT_LIST}" .
FIRST_FILE=$(head -n 1 "${INPUT_LIST}")

cmsDriver.py NANO \
  --era Run3_2024 \
  --conditions 150X_dataRun3_v2 \
  --datatier NANOAOD \
  --eventcontent NANOAOD \
  --step NANO \
  --python_filename "${CFG_FILE}" \
  --filein "root://cmsxrootd.fnal.gov/${FIRST_FILE}" \
  --fileout "file:${OUTPUT_FILE}" \
  --data \
  --scenario pp \
  --number -1 \
  --nThreads 8 \
  --no_exec

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate Data config file"
    exit 1
fi

echo "Data config file generated successfully: ${CFG_FILE}"
echo ""

# ============================================
# Apply custom skimming to config
# ============================================
echo "Applying custom skimming configuration..."

# Copy customization module to work directory
cp "$CUSTOMIZE_FILE" .

# Append custom functions to the generated config file
cat >> ${CFG_FILE} << 'CUSTOMEOF'

# ========== CUSTOM SKIMMING CONFIGURATION ==========
# Import custom functions
import sys
sys.path.insert(0, '.')
from cmsskim_customize import SetupAK8ReclusterSubjets, SetupSkim_HLTSingleMuonOneFatJet, SetupGloParTForAK8Subjets

# Apply customizations
process = SetupSkim_HLTSingleMuonOneFatJet(process)
process = SetupGloParTForAK8Subjets(process)
process = SetupAK8ReclusterSubjets(process)

CUSTOMEOF

echo "Custom skimming applied to config"
echo ""

echo "Uploading file list present in the dataset"
echo ""
cat >> "${CFG_FILE}" <<PYCODE

# Complete input list inserted by run_cmsdriver_data.sh
_input_file_list = "${INPUT_LIST}"

with open(_input_file_list, "r") as _input_handle:
    _input_files = [
        "root://cmsxrootd.fnal.gov/" + line.strip()
        for line in _input_handle
        if line.strip()
    ]

process.source.fileNames = cms.untracked.vstring(*_input_files)
process.NANOAODoutput.fileName = cms.untracked.string(
    "file:${OUTPUT_FILE}"
)

PYCODE

# Copy configuration file
if [ -f "${CFG_FILE}" ]; then
    echo "Copying ${CFG_FILE} to EOS..."
    xrdcp -f ${CFG_FILE} ${EOS_ENDPOINT}/$EOS_OUTPUT_BASE/${CFG_FILE}
    if [ $? -eq 0 ]; then
        echo "✓ ${CFG_FILE} successfully copied to EOS"
    else
        echo "ERROR: Failed to copy config file"
        exit 1
    fi
fi

# ============================================
# Execute cmsRun for Data
# ============================================
echo "Executing Data NanoAOD job..."
echo "Config file: ${CFG_FILE}"
echo "Number of input files: $(wc -l < "${INPUT_LIST}")"
echo ""

cmsRun "${CFG_FILE}" #2>&1 | tee data_job_${JOBID}.log

CMSRUN_EXIT_CODE=$?

echo ""
echo "=========================================="
echo "Data Job Execution Completed"
echo "Exit Code: $CMSRUN_EXIT_CODE"
echo "End time: $(date)"
echo "=========================================="

if [ $CMSRUN_EXIT_CODE -ne 0 ]; then
    echo "ERROR: cmsRun failed with exit code $CMSRUN_EXIT_CODE"
    exit 1
fi

# ============================================
# Copy output files to EOS
# ============================================
echo ""
echo "Copying output files to EOS..."
echo "Source: $LOCAL_WORK_DIR"
echo "Destination: $EOS_OUTPUT_BASE"
echo ""

# Copy NanoAOD root file
if [ -f "${OUTPUT_FILE}" ]; then
    echo "Copying ${OUTPUT_FILE} to EOS..."
    xrdcp -f ${OUTPUT_FILE} ${EOS_ENDPOINT}/$EOS_OUTPUT_BASE/${OUTPUT_FILE}
    if [ $? -eq 0 ]; then
        echo "✓ ${OUTPUT_FILE} successfully copied to EOS"
    else
        echo "ERROR: Failed to copy ${OUTPUT_FILE}"
        exit 1
    fi
else
    echo "WARNING: ${OUTPUT_FILE} not found"
fi

# Copy log file
#if [ -f "data_job_${JOBID}.log" ]; then
#    echo "Copying data_job_${JOBID}.log to EOS..."
#    xrdcp -f data_job_${JOBID}.log ${EOS_ENDPOINT}/$EOS_OUTPUT_BASE/data_job_${JOBID}.log
#    if [ $? -eq 0 ]; then
#        echo "✓ data_job_${JOBID}.log successfully copied to EOS"
#    else
#        echo "WARNING: Failed to copy log file (non-critical)"
#    fi
#fi

echo ""
echo "=========================================="
echo "All output files copied to EOS"
echo "EOS Path: $EOS_OUTPUT_BASE"
echo "=========================================="

# Clean up work directory
echo "Cleaning up work directory..."
cd $OLDPWD
rm -rf $LOCAL_WORK_DIR
echo "✓ Cleanup complete"

echo ""
echo "=========================================="
echo "Data Job Complete - All files in EOS"
echo "=========================================="

exit 0
