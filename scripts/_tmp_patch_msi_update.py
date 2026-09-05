from pathlib import Path

path = Path("src/cinepulse/update_manager.py")
text = path.read_text(encoding="utf-8")
old = '            "& $Msiexec /i $Msi /passive /norestart /L*v $Log",\n'
new = '            "& $Msiexec /i $Msi /passive /norestart CINEPULSE_SKIP_BOOTSTRAP=1 /L*v $Log",\n'
if text.count(old) != 1:
    raise SystemExit("MSI handoff anchor mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("CINEPULSE_MSI_UPDATE_HANDOFF_HARDENED")
