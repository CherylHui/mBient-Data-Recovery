# Mbient USB Recovery — macOS User Guide

Last updated: 19 November 2026  
Tool: `mbient_usb_recovery_v1_1.py` (existing experimental release)  
Audience: operators using another Mac, including a Mac without Python or development tools installed.

> This guide documents the existing recovery workflow. It is not a new software release and does not certify every Mac, sensor or firmware combination. The person handing over the workflow must supply the final recovery script. Check its `--help` output before use. If the script and this guide disagree, stop and check the version rather than guessing options or removing safety checks.

## Contents

1. Safety and stop conditions
2. What you need
3. Installing Python from scratch
4. Preparing the local working folder
5. Creating the environment and installing pyserial
6. Checking the installation
7. Recovering data from each sensor
8. Outputs, completion checks and backups
9. Offline decoding and timestamp limitations
10. Troubleshooting: installation and computer setup
11. Troubleshooting: USB and recovery
12. Moving to another Mac and reporting problems
13. Everyday command reference
14. Official installation references

## 1. Safety and stop conditions

### 1.1 Retrieve is not a non-destructive file copy

The `retrieve` confirmation prompt states that, after consent, the tool will:

1. Stop logging and ACC/gyroscope acquisition.
2. Flush pending NAND writes.
3. Read, save and confirm pages.
4. Permanently confirm saved pages. Do not assume that confirmed pages can subsequently be read from the sensor again.

Before proceeding, the person responsible for the data must confirm that it is acceptable to stop the recording and that no other recovery session has already confirmed pages from this recording.

### 1.2 Stop if any of the following applies

- The sensor identity is unclear, or its physical label does not match the USB/firmware serial records.
- You do not know whether pages from the same recording have already been downloaded and confirmed.
- `inspect` reports an unsupported profile, a timeout or an unexpected response.
- A device lock or previous-attempt marker exists.
- A disconnection, power failure, timeout, Ctrl-C or other error occurs after recovery has been authorised and started.
- A disk write fails, free space is insufficient, or the output location is unclear.

Keep the entire working folder and the error output, and contact the person responsible for the data. Do not simply rerun `retrieve`, reset the sensor, clear loggers, delete locks, change the root folder or use another computer to bypass the problem.

### 1.3 Separate installation problems from recovery failures

Python, pip and file-path problems can be addressed using this guide before recovery starts.

If recovery has already started, even a subsequent computer or Python error must initially be treated as an interrupted recovery. Repairing the computer does not make it safe to download the recording again.

## 2. What you need

| Item | Required? | Notes |
|---|---|---|
| Mac and Terminal | Yes | Terminal is included with macOS. |
| Python 3 | Yes | Prefer the version validated by the person handing over the workflow. This guide uses Python 3.10+ as a setup baseline; it does not certify every newer version. |
| pyserial | Yes | The package name is `pyserial`; its Python import name is `serial`. |
| Final recovery script | Yes | Obtain the actual `.py` file, not just an upgrade script. |
| USB cable supporting data transfer | Yes | A charging-only cable is not sufficient. |
| Suitable USB adaptor | If needed | Use a stable connection. |
| Local storage and a separate backup drive | Yes | Preserve raw data and reports, not just CSV files. |
| Internet connection | Usually for initial installation | Used to obtain Python and packages, not to upload experimental data. |
| Administrator or IT assistance | Depending on policy | Installing the official Python package may require administrator authorisation. |

You do not need Homebrew, Anaconda, VS Code, Excel or a full Xcode installation for this workflow. Once Python and pyserial are installed, use Terminal. Additional packages for plotting or six-event comparisons are outside the scope of this recovery guide.

Do not infer compatibility from the Mbient brand alone. The existing workflow concerns MetaMotionS, firmware 1.7.2 and recognised ACC logger configurations. The actual `inspect` result and the script's safety checks determine whether a configuration is supported. Do not remove checks to force another device to work.

## 3. Installing Python from scratch

### 3.1 Open Terminal

Press Command + Space, type `Terminal`, then press Return.

Copy only the commands inside code blocks. Do not copy somebody else's prompt, such as `(.venv) username@Mac %`. A backslash used for line continuation must be the final character on the line, with no trailing spaces.

### 3.2 Check before installing

```bash
python3 --version
command -v python3
```

- If a suitable Python version is available, record the version and path, then continue.
- If the command is not found, the version is unsuitable, or macOS asks to install developer tools, follow the installation steps below.
- Do not alter or delete `/usr/bin/python3`, or upgrade/remove Python installations used by other institutional projects.

### 3.3 Recommended installation method for a new operator

1. Visit the official Python macOS download page:
   https://www.python.org/downloads/macos/
2. Prefer a stable version already validated for this workflow. Check that its installer supports the Mac's version of macOS.
3. Download the official macOS `.pkg` installer. Current universal2 installers support compatible Intel and Apple Silicon Macs.
4. Open the installer and follow its instructions. Obtain IT assistance if administrator authorisation is required.
5. In Applications, open the matching `Python 3.x` folder and run `Install Certificates.command`. Use the folder corresponding to the version you installed.
6. Close and reopen Terminal.
7. Check again:

```bash
python3 --version
command -v python3
```

Do not obtain installers from unknown websites, disable Gatekeeper or System Integrity Protection, or run an untrusted `curl ... | bash` command.

For a computer without internet access, ask IT to prepare an approved installer and compatible pyserial wheel in advance. See Section 10.9.

## 4. Preparing the local working folder

### 4.1 Standard location for a new installation

Use:

```text
~/Mbient_USB_recovery
```

`$HOME` automatically refers to the current user's home folder. Do not substitute the original operator's `/Users/hwh` path.

```bash
mkdir -p "$HOME/Mbient_USB_recovery"
cd "$HOME/Mbient_USB_recovery"
open .
```

Use Finder to place these files in the folder that opens:

```text
README.md
mbient_usb_recovery_v1_1.py
```

- Obtain the final script from the person handing over the workflow. `upgrade_mbient_to_v1_1.py` alone is not sufficient.
- Check that the script has not become `.py.txt`, an HTML page or a rich-text document.
- Do not double-click the script to run it. Use the Terminal commands in this guide.
- Do not copy the old computer's `.venv`. Recreate the environment on the new Mac.

```bash
pwd
ls -l mbient_usb_recovery_v1_1.py
shasum -a 256 mbient_usb_recovery_v1_1.py
```

Compare the hash with the handover record.

### 4.2 Keep experimental data local

Check that the working folder is not uploaded by iCloud, OneDrive, Dropbox or another synchronisation service. Avoid using Desktop or Documents by default, as they may be synchronised. Check the actual operating system settings and institutional policies rather than assuming a folder is local-only.

Keep experimental data processing on the local computer. Do not upload raw data to external services for troubleshooting.

### 4.3 Existing recovery workspaces are an exception

The location above is for a new setup. If recovery for a recording has already started in another folder, do not change its root simply to match this README.

Locks and attempt records are associated with the workspace. Changing the root does not make the sensor fresh. Ask the person responsible for the data to review the original workspace first.

## 5. Creating the environment and installing pyserial

Perform this setup once on a new computer, or when an inactive environment has been identified as needing repair.

```bash
cd "$HOME/Mbient_USB_recovery"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyserial
```

If a validated `requirements.txt` has been provided, replace the last command with:

```bash
python -m pip install -r requirements.txt
```

You do not need to use both installation methods. Install inside `.venv`; do not use `sudo pip` or `--break-system-packages`.

Check the installation:

```bash
python -c 'import sys; print(sys.executable); print(sys.version)'
python -m pip --version
python -c 'import serial; print(serial.__version__); print(serial.__file__)'
```

The Python executable should be this working folder's `.venv/bin/python`. The serial package should be inside this `.venv`, not an unexpected local file called `serial.py`.

## 6. Checking the installation

Do not start a sensor download merely to test the installation.

```bash
cd "$HOME/Mbient_USB_recovery"
source .venv/bin/activate
python mbient_usb_recovery_v1_1.py --help
```

Check that the help output lists the appropriate `scan`, `inspect`, `retrieve` and `decode` commands. Check their actual options:

```bash
python mbient_usb_recovery_v1_1.py inspect --help
python mbient_usb_recovery_v1_1.py retrieve --help
python mbient_usb_recovery_v1_1.py decode --help
```

If the supplied release supports a version option, record it:

```bash
python mbient_usb_recovery_v1_1.py --version
```

If the option is unsupported, check the file hash and supplied release. Renaming a file is not an upgrade.

Record the environment:

```bash
python -m pip freeze > requirements-local.txt
python --version > python-version.txt
shasum -a 256 mbient_usb_recovery_v1_1.py > tool-sha256.txt
```

For every new Mac, complete the `--help`, `scan` and `inspect` checks. A successful import alone does not validate USB recovery.

## 7. Recovering data from each sensor

### 7.1 Whenever you open a new Terminal session

```bash
cd "$HOME/Mbient_USB_recovery"
source .venv/bin/activate
```

Check the recording's recovery history first. Connect the Mac to power, provide sufficient free space, and close MetaBase or other applications that may use the device. Connect one sensor at a time. Do not close the lid or allow the Mac to sleep during recovery.

Check available storage if needed:

```bash
df -h "$HOME/Mbient_USB_recovery"
```

There is no single minimum capacity suitable for every recording. Allow space for raw data, CSVs, audit files and additional decoding runs.

### 7.2 Scan: list USB devices

```bash
python mbient_usb_recovery_v1_1.py scan
```

This is not a Bluetooth scan. Expected output includes a serial port, full USB serial and device description.

If no matching device appears, list all descriptors:

```bash
python mbient_usb_recovery_v1_1.py scan --all
```

Do not send commands to an unidentified device port.

### 7.3 Inspect: check identity and supported configuration

```bash
python mbient_usb_recovery_v1_1.py inspect \
  --root "$HOME/Mbient_USB_recovery"
```

Record the displayed `OUTPUT` folder, `Identity`, full `USB serial` and `Supported profile`.

An example from the existing workflow is:

```text
Identity: MbientLab MetaMotionS 8 0.1 1.7.2 056C9F
USB serial: CC86B9A0ADB4
```

This is an example, not the expected identity of every sensor. Firmware serial and USB serial are different fields and need not match. A short serial suffix is not a participant ID.

The existing Inspect completion message is:

```text
Metadata saved. No stop, NAND flush, readout or page confirm sent.
```

Stop here for a manual check. Do not continue if the profile is unsupported, a timeout occurs, the identity is wrong, or the recording's fresh status is uncertain.

### 7.4 Retrieve: stop logging and confirm saved pages only after authorisation

```bash
python -u mbient_usb_recovery_v1_1.py retrieve \
  --root "$HOME/Mbient_USB_recovery"
```

Check the identity again. If the actual prompt says:

```text
Type FRESH 056C9F to consent:
```

enter the following only if the fresh-recording conditions have been verified:

```text
FRESH 056C9F
```

Use the serial shown in the current prompt, not the example. If unsure, cancel before giving consent and consult the person responsible for the data.

Once recovery starts, do not unplug USB, close the lid, reset the sensor, open competing sensor applications or start another retrieval. Do not provide fresh consent again after an error.

If reliable records establish the historical accelerometer range, and the supplied release supports the option, an alternative command is:

```bash
python -u mbient_usb_recovery_v1_1.py retrieve \
  --root "$HOME/Mbient_USB_recovery" \
  --range-g 2
```

This is an alternative chosen before starting, not a second download to run afterwards. Do not guess the range simply to make the magnitude look plausible.

## 8. Outputs, completion checks and backups

### 8.1 Preserve the entire output folder

Typical outputs include the following; the exact contents depend on the release and outcome:

```text
inspect_.../
    metadata.json
    ...
retrieve_.../
    metadata.json
    received.bin
    journal.jsonl
    page_*.bin
    raw_manifest.json
    download_report.json
    summary.json
    decoded_.../
        *_CANDIDATE_ESTIMATED.csv
        *_audit.csv
        decode_report.json
        ...
device_locks/
    ...
```

After an error, only some files may exist. A missing summary does not prove that no pages were confirmed. Trailing data not yet saved as a page may still exist in the received byte stream, so preserve more than the page files or CSVs.

Keep separate logger groups separate. Two CSV files do not necessarily represent two independent physical sample sequences. Do not automatically merge or deduplicate them.

### 8.2 Check reports, not just whether a CSV exists

Replace the quoted example below with the actual path displayed by the tool. `/actual/retrieve_folder` is a placeholder:

```bash
python -m json.tool "/actual/retrieve_folder/summary.json"
```

Also inspect `decode_report.json` in each decoded folder.

Check:

- Whether readout completed according to the tool's rules.
- Raw entry counts, saved entries and page save/confirmation status.
- Any trailing entries not saved into page files.
- Differences between the sensor-reported count and the received count.
- Each group's CSV completion status, sample count and errors.
- UID, tick, pairing or timestamp-gap warnings.
- Whether historical completeness remains unverified.

`readout_finished` or `csv_complete` does not prove zero historical loss, correct UTC or precise synchronisation. A count discrepancy must not automatically be dismissed as padding or labelled as loss. Preserve the evidence.

### 8.3 Back up and record the outcome

After the command finishes and the Terminal prompt returns, copy the complete outputs, inspection records, locks, version and environment records to a separate reliable drive. Verify the backup before considering reuse of the sensor.

For each sensor, record at least: full USB serial, firmware serial, physical label, recording name, operator, computer, root folder, output path, completion/error status, whether any pages were confirmed, and backup location.

## 9. Offline decoding and timestamp limitations

If raw readout finished but the decoder or a known range needs adjustment, prefer decoding the saved raw data rather than downloading from the sensor again:

```bash
python mbient_usb_recovery_v1_1.py decode \
  "/actual/retrieve_folder" \
  --range-g 2
```

Check `decode --help` first. If retrieval was interrupted, ask the person responsible for the data to review the raw files; do not assume ordinary decoding will recover every unfinished tail.

CSV interpretation:

- `elapsed (s)` is the decoder's relative time, not H10/LSL experiment time.
- `epoch (ms)` and `timestamp (+0000)` depend on historical clock assumptions; do not treat them as universally verified UTC.
- The range currently reported by the device does not prove the historical range was identical.
- Preserve and investigate large forward gaps. Do not interpolate across hours-long gaps.
- Six drop markers can support event-level comparisons, not automatically sample-level synchronisation, participant identification or proof of zero loss.

## 10. Troubleshooting: installation and computer setup

Do not repair or replace an environment while recovery is running. If recovery was interrupted, preserve its outputs and obtain a review before any further download, even after the environment has been repaired.

### 10.1 `python3: command not found`, or a developer-tools installation prompt

Install official Python as described in Section 3, then reopen Terminal. Do not install all of Xcode merely for this workflow.

```bash
command -v python3
python3 --version
```

If Python is installed but unavailable, ask IT to check the installer and PATH rather than modifying the system Python blindly.

### 10.2 `python: command not found`

Use `python3` before creating the environment. Use `python` after activating `.venv`:

```bash
cd "$HOME/Mbient_USB_recovery"
source .venv/bin/activate
python --version
```

### 10.3 Missing `.venv/bin/activate`, bad interpreter, or an environment copied from another Mac

Check your location first:

```bash
pwd
ls -la
```

Do not delete the workspace. If the environment has been confirmed as faulty and no recovery is running, preserve it and create a new one:

```bash
cd "$HOME/Mbient_USB_recovery"
type deactivate >/dev/null 2>&1 && deactivate
if [ -d .venv ]; then
  mv .venv ".venv_old_$(date +%Y%m%d_%H%M%S)"
fi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyserial
```

Use the validated requirements file instead if provided. This repairs Python only: it does not remove locks or restore sensor pages.

### 10.4 `No module named pip`

After confirming that the correct environment is active:

```bash
python -m ensurepip --upgrade
python -m pip --version
python -m pip install pyserial
```

If `ensurepip` is also missing, recreate the environment using a complete official Python installation or ask IT. Do not download an unknown pip installation script.

### 10.5 `No module named serial`

```bash
cd "$HOME/Mbient_USB_recovery"
source .venv/bin/activate
python -m pip install pyserial
python -c 'import serial; print(serial.__version__); print(serial.__file__)'
```

Install `pyserial`, not `serial`. Installing into another Python or Conda environment does not fix this environment.

### 10.6 `module serial has no attribute Serial`, or the wrong module is imported

```bash
python -m pip show pyserial
python -m pip show serial
python -c 'import serial; print(serial.__file__)'
```

If the unrelated `serial` package was mistakenly installed in this dedicated `.venv`, repair it with:

```bash
python -m pip uninstall serial
python -m pip install --force-reinstall pyserial
```

If the import points to a local `serial.py` file or `serial` folder, have it identified before renaming or removing anything. Do not uninstall packages from somebody else's shared system environment.

### 10.7 `externally-managed-environment` or a pip permission error

Check whether you are using the intended environment:

```bash
python -c 'import sys; print(sys.executable); print(sys.prefix != sys.base_prefix)'
python -m pip --version
```

Expect a path inside this project's `.venv` and the value `True`. Otherwise, reactivate or recreate the dedicated environment.

Do not bypass the problem using `sudo pip`, `chmod 777` or `--break-system-packages`.

### 10.8 `CERTIFICATE_VERIFY_FAILED`, proxy, DNS or network timeout errors

- Check the Mac's date/time and approved network connection.
- For a python.org installation, run `Install Certificates.command` from the matching Python folder in Applications.
- Ask IT to configure institutional proxies or certificates. Do not disable SSL verification or use `--trusted-host` as a general workaround.
- This step downloads software packages. It does not require sensor data to be supplied or uploaded.

### 10.9 Fully offline installation

Ask IT or the workflow owner to obtain the official Python installer and prepare the package on an internet-connected computer:

```bash
python3 -m pip download --only-binary=:all: --dest wheelhouse pyserial
```

Use validated package versions where available and check hashes. Transfer the installer, `wheelhouse`, final script and README through an approved method.

On the offline Mac, install Python, create and activate `.venv`, then run:

```bash
python -m pip install --no-index --find-links ./wheelhouse pyserial
```

The `wheelhouse` folder must be in the current directory and contain a compatible wheel. Other, non-pure-Python packages may require platform-specific files. Do not substitute an arbitrary computer's `.venv`.

### 10.10 `can't open file` or `No such file or directory`

```bash
cd "$HOME/Mbient_USB_recovery"
pwd
ls -la
ls -l mbient_usb_recovery_v1_1.py
```

Check whether the script is still in Downloads, has an added suffix such as `(1)`, or has become `.py.txt`. Use Finder to place the correct file in the working folder. Do not rename an unrelated file to impersonate the script.

### 10.11 `SyntaxError`, HTML or RTF content in the script

Possible causes include an unsuitable Python version, a downloaded web page, incomplete copying or rich-text formatting. Check Python and the script hash, then obtain the complete plain-text `.py` from the workflow owner. Do not edit the script during recovery.

### 10.12 Terminal shows `>>>`, `quote>` or waits for another line

- `>>>` means you entered the Python interactive shell. Type `exit()` before entering shell commands.
- `quote>` or `dquote>` usually means an unmatched quotation mark.
- For continued commands, paste the whole block and avoid smart quotes or spaces after a final backslash.

Only use Ctrl-C to cancel incomplete input when you have confirmed that no recovery is running. It is not a routine troubleshooting step during recovery.

### 10.13 macOS security warnings or a managed computer that blocks installation

Check that the installer is official and institutionally approved. Ask IT for help. Do not remove quarantine attributes, disable Gatekeeper/System Integrity Protection or grant unnecessary Full Disk Access to Terminal.

If macOS asks whether to allow a USB accessory, follow institutional policy. Do not use sudo to force access to an unexplained USB device.

## 11. Troubleshooting: USB and recovery

### 11.1 `Matching/listed ports: 0`

Only if retrieval has not started and no interrupted recovery needs review:

1. Check the sensor model and use a known data-capable USB cable.
2. Try a known working cable or port; avoid unstable hubs.
3. Unlock the Mac and allow the USB accessory if required and permitted.
4. List descriptors again:

```bash
python mbient_usb_recovery_v1_1.py scan --all
python -m serial.tools.list_ports -v
```

If the device remains absent, ask the workflow owner or IT to investigate the USB connection. Do not install unknown USB drivers.

### 11.2 `Permission denied`, `Resource busy` or failure to open a port

First confirm that no other recovery is running. Close MetaBase, serial monitors or other applications that may hold the device. Do not forcibly terminate an unidentified process.

To check which process holds a port, replace the placeholder with the actual port from scan:

```bash
lsof "/dev/cu.usbmodemACTUAL_PORT"
```

If recovery has already started, do not use unplugging/reconnecting as a retry procedure.

### 11.3 Unsupported Inspect result, empty loggers or length 0

Stop and preserve the current metadata. Check firmware, profile, full USB serial and previous export records.

Empty definitions or zero length do not independently prove that no recording ever existed. Data may have been exported or the configuration may be unsupported. Do not create loggers, start a recording, reset or clear the sensor to 'repair' it. Check the current sensor's metadata, not a hard-coded path from the previous device.

### 11.4 Inspect timeout

Preserve the output and check the script version and device profile. Do not treat a timeout as a completed inspection. If only Inspect ran and page confirmation definitely did not start, the workflow owner can investigate the connection. Do not jump to Retrieve as a test.

### 11.5 Existing attempt marker or device lock

Locate the original recovery folder and handover record. Do not delete locks, change the root or computer, or alter identifiers. The absence of a lock on a new computer does not establish fresh status.

### 11.6 Disconnection, timeout, Ctrl-C, sleep or disk-full error during Retrieve

Stop further operations and preserve:

- Complete retrieve and inspect folders, plus `device_locks`.
- `received.bin`, page files, manifests, journals and all error/completion reports.
- Full Terminal error text and the time of the failure.
- Sensor identity, original computer and original root path.

Some pages may already have been confirmed. The outcome of the last confirmation may also be uncertain. Do not automatically rerun a fresh recovery. Have the raw files and journal reviewed first.

### 11.7 Raw readout succeeds but some or all CSV decoding fails

Do not download the sensor again. Review each group's decoding report for UID, tick, pairing or range issues. Keep all raw data and prioritise offline decoder repair or segmentation.

### 11.8 Count discrepancies, large gaps or implausible UTC

Preserve the originals and flag the issue. Do not fill with zeros, interpolate across large gaps or shift timestamps merely to produce a plausible-looking precise timeline. Check each logger group separately.

## 12. Moving to another Mac and reporting problems

### 12.1 Handover checklist

Transfer:

- Final `.py`, README and script SHA-256.
- Validated Python/package version records.
- All relevant inspect and retrieve folders, including failed attempts, and `device_locks`.
- Device/recording records, page-confirmation history and backup records.

Do not hand over only CSVs or an upgrade script. Do not treat a copied `.venv` as a completed installation.

### 12.2 Collecting diagnostics locally

When no recovery is running:

```bash
cd "$HOME/Mbient_USB_recovery"
source .venv/bin/activate
sw_vers
uname -m
python --version
python -c 'import sys; print(sys.executable)'
python -m pip --version
python -m pip show pyserial
shasum -a 256 mbient_usb_recovery_v1_1.py
```

Also record the full error, command entered, output folder, sensor serial, and whether FRESH consent was entered or page confirmation had started.

Diagnostic output may contain usernames, paths and device identifiers. Share it only with authorised personnel. Do not post raw physiological or movement data publicly or upload it to external services.

## 13. Everyday command reference

Use this section only after initial installation and checks.

### A. Activate, scan and inspect

```bash
cd "$HOME/Mbient_USB_recovery"
source .venv/bin/activate
python mbient_usb_recovery_v1_1.py scan
python mbient_usb_recovery_v1_1.py inspect \
  --root "$HOME/Mbient_USB_recovery"
```

Pause for manual identity, profile and fresh-status checks.

### B. Retrieve only after those checks pass

```bash
python -u mbient_usb_recovery_v1_1.py retrieve \
  --root "$HOME/Mbient_USB_recovery"
```

Enter only the `FRESH <serial>` requested by the current prompt. Do not interrupt recovery or rerun it after an error.

### C. Finish

Check reports → preserve all raw data → back up to a separate drive → record the outcome → proceed to the next sensor only afterwards.

Leave the environment when finished:

```bash
deactivate
```

## 14. Official installation references

- Python on macOS and certificate setup: https://docs.python.org/3/using/mac.html
- Official macOS installers: https://www.python.org/downloads/macos/
- Virtual environments and portability limitations: https://docs.python.org/3/library/venv.html
- pyserial installation and module naming: https://pyserial.readthedocs.io/en/latest/pyserial.html

This README does not install software or modify a sensor. The operator must complete the steps on the target Mac, validate the environment and perform the safety checks before starting recovery.
