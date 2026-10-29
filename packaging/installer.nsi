Unicode true
RequestExecutionLevel user
SetCompressor zlib
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!define APP_ID "VLADMACC.CodexUsageWidget"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\VLADMACC.CodexUsageWidget"
Name "GPTOKEN — Codex Usage Widget"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\VLADMACC\CodexUsageWidget"
BrandingText "VLADMACC · дизайн-студия"
Icon "${APP_ICON}"
UninstallIcon "${APP_ICON}"
VIProductVersion "5.1.1.0"
VIAddVersionKey "ProductName" "GPTOKEN"
VIAddVersionKey "FileDescription" "GPTOKEN installer"
VIAddVersionKey "CompanyName" "VLADMACC"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2026 VLADMACC. All rights reserved."
VIAddVersionKey "FileVersion" "${VERSION}"
Var TestMode
Var Options
Var Entry
Var Search
Var Marker
Var StopResult

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\CodexUsageWidget.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Открыть виджет"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!define MUI_UNCONFIRMPAGE_TEXT_TOP "Будут удалены только файлы GPTOKEN. Настройки и история в профиле пользователя сохранятся."
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"

Function .onInit
  StrCpy $TestMode "0"
  SetShellVarContext current
  ${GetParameters} $Options
  ${GetOptions} $Options "/TEST=" $TestMode
  ${If} $TestMode != "1"
    StrCpy $TestMode "0"
  ${EndIf}
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Требуется Windows x64." /SD IDOK
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "Требуется Windows 10 или новее." /SD IDOK
    Abort
  ${EndIf}
FunctionEnd

Function VerifyDestination
  ; Empty folders are allowed; a non-empty folder must carry our exact marker.
  FindFirst $Search $Entry "$INSTDIR\*"
  loop:
    ${If} $Entry == ""
      Goto empty
    ${EndIf}
    ${If} $Entry != "."
    ${AndIf} $Entry != ".."
      FindClose $Search
      ClearErrors
      FileOpen $Marker "$INSTDIR\.vladmacc-install" r
      IfErrors reject
      FileRead $Marker $Entry
      FileClose $Marker
      StrCmp $Entry "${APP_ID}" accepted reject
    ${EndIf}
    FindNext $Search $Entry
    Goto loop
  empty:
    FindClose $Search
    Goto accepted
  reject:
    MessageBox MB_ICONSTOP "Выбранная папка содержит посторонние файлы. Выберите новую пустую папку для GPTOKEN." /SD IDOK
    SetErrorLevel 2
    Abort
  accepted:
FunctionEnd

Function .onVerifyInstDir
  Call VerifyDestination
FunctionEnd

Section "GPTOKEN (обязательно)" Main
  SectionIn RO
  Call VerifyDestination
  IfFileExists "$INSTDIR\CodexUsageWidget.exe" 0 install
    ${If} $TestMode == "1"
      ExecWait '"$INSTDIR\CodexUsageWidget.exe" --quit --data-dir "$INSTDIR\qa-data"' $StopResult
    ${Else}
      ExecWait '"$INSTDIR\CodexUsageWidget.exe" --quit' $StopResult
    ${EndIf}
    ${If} $StopResult != 0
      MessageBox MB_ICONSTOP "Закройте виджет и повторите установку." /SD IDOK
      Abort
    ${EndIf}
  install:
    SetOutPath "$INSTDIR"
    File /r "${PAYLOAD}\*"
    FileOpen $Marker "$INSTDIR\.vladmacc-install" w
    FileWrite $Marker "${APP_ID}"
    FileClose $Marker
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    ${If} $TestMode == "1"
      FileOpen $Marker "$INSTDIR\.vladmacc-test-install" w
      FileWrite $Marker "1"
      FileClose $Marker
    ${Else}
      CreateDirectory "$SMPROGRAMS\VLADMACC GPTOKEN"
      CreateShortcut "$SMPROGRAMS\VLADMACC GPTOKEN\GPTOKEN.lnk" "$INSTDIR\CodexUsageWidget.exe"
      CreateShortcut "$SMPROGRAMS\VLADMACC GPTOKEN\Настройки.lnk" "$INSTDIR\CodexUsageWidget.exe" "--settings"
      WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "GPTOKEN — Codex Usage Widget"
      WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
      WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "VLADMACC"
      WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
      WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\CodexUsageWidget.exe"
      WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
      WriteRegStr HKCU "${UNINSTALL_KEY}" "URLInfoAbout" "https://github.com/vladmacc1/gptoken"
      WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
      WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
    ${EndIf}
SectionEnd

Section /o "Ярлык на рабочем столе" Desktop
  ${If} $TestMode != "1"
    CreateShortcut "$DESKTOP\GPTOKEN.lnk" "$INSTDIR\CodexUsageWidget.exe"
  ${EndIf}
SectionEnd

Section /o "Запускать вместе с ChatGPT после входа в Windows" Startup
  ${If} $TestMode != "1"
    CreateShortcut "$SMSTARTUP\VLADMACC GPTOKEN.lnk" "$INSTDIR\CodexUsageWidget.exe" "--watch"
  ${EndIf}
SectionEnd

Function un.onInit
  SetShellVarContext current
  ClearErrors
  FileOpen $Marker "$INSTDIR\.vladmacc-install" r
  IfErrors reject
  FileRead $Marker $Entry
  FileClose $Marker
  StrCmp $Entry "${APP_ID}" accepted reject
  reject:
    MessageBox MB_ICONSTOP "Не найдена отметка установки GPTOKEN. Файлы не будут удалены." /SD IDOK
    Abort
  accepted:
    StrCpy $TestMode "0"
    IfFileExists "$INSTDIR\.vladmacc-test-install" 0 +2
      StrCpy $TestMode "1"
FunctionEnd

Section "Uninstall"
  ${If} $TestMode == "1"
    ExecWait '"$INSTDIR\CodexUsageWidget.exe" --quit --data-dir "$INSTDIR\qa-data"' $StopResult
  ${Else}
    ExecWait '"$INSTDIR\CodexUsageWidget.exe" --quit' $StopResult
  ${EndIf}
  ${If} $StopResult != 0
    MessageBox MB_ICONSTOP "Закройте виджет перед удалением." /SD IDOK
    Abort
  ${EndIf}
  !include "${UNINSTALL_FILES}"
  Delete "$INSTDIR\.vladmacc-install"
  Delete "$INSTDIR\.vladmacc-test-install"
  Delete "$INSTDIR\Uninstall.exe"
  ${If} $TestMode != "1"
    Delete "$DESKTOP\GPTOKEN.lnk"
    Delete "$SMSTARTUP\VLADMACC GPTOKEN.lnk"
    Delete "$SMPROGRAMS\VLADMACC GPTOKEN\GPTOKEN.lnk"
    Delete "$SMPROGRAMS\VLADMACC GPTOKEN\Настройки.lnk"
    RMDir "$SMPROGRAMS\VLADMACC GPTOKEN"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
  ${EndIf}
  RMDir "$INSTDIR"
SectionEnd
