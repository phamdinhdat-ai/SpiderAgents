; openspider Desktop NSIS installer. Run makensis from repo root after
; building dist/win-unpacked (see scripts/pack/build_win.ps1).
; Usage: makensis /Dopenspider_VERSION=1.2.3 /DOUTPUT_EXE=dist\openspider-Setup-1.2.3.exe scripts\pack\desktop.nsi

!include "MUI2.nsh"
!define MUI_ABORTWARNING
; Use custom icon from unpacked env (copied by build_win.ps1)
!define MUI_ICON "${UNPACKED}\icon.ico"
!define MUI_UNICON "${UNPACKED}\icon.ico"

!ifndef openspider_VERSION
  !define openspider_VERSION "0.0.0"
!endif
!ifndef OUTPUT_EXE
  !define OUTPUT_EXE "dist\openspider-Setup-${openspider_VERSION}.exe"
!endif

Name "openspider Desktop"
OutFile "${OUTPUT_EXE}"
InstallDir "$LOCALAPPDATA\openspider"
InstallDirRegKey HKCU "Software\openspider" "InstallPath"
RequestExecutionLevel user

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

; Pass /DUNPACKED=full_path from build_win.ps1 so path works when cwd != repo root
!ifndef UNPACKED
  !define UNPACKED "dist\win-unpacked"
!endif

Section "openspider Desktop" SEC01
  SetOutPath "$INSTDIR"
  File /r "${UNPACKED}\*.*"
  WriteRegStr HKCU "Software\openspider" "InstallPath" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Main shortcut - uses VBS to hide console window
  CreateShortcut "$SMPROGRAMS\openspider Desktop.lnk" "$INSTDIR\openspider Desktop.vbs" "" "$INSTDIR\icon.ico" 0
  CreateShortcut "$DESKTOP\openspider Desktop.lnk" "$INSTDIR\openspider Desktop.vbs" "" "$INSTDIR\icon.ico" 0
  
  ; Debug shortcut - shows console window for troubleshooting
  CreateShortcut "$SMPROGRAMS\openspider Desktop (Debug).lnk" "$INSTDIR\openspider Desktop (Debug).bat" "" "$INSTDIR\icon.ico" 0
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\openspider Desktop.lnk"
  Delete "$SMPROGRAMS\openspider Desktop (Debug).lnk"
  Delete "$DESKTOP\openspider Desktop.lnk"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\openspider"
SectionEnd
