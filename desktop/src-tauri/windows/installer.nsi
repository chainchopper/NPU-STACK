; NPU-STACK NSIS Installer Template
; Based on Tauri v2 default NSIS template with NPU-STACK customizations

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define PRODUCT_NAME "NPU-STACK"
!define PRODUCT_PUBLISHER "Fanalogy"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_WEB_SITE "https://github.com/chainchopper/NPU-STACK"
!define PRODUCT_DIR_REGKEY "Software\NPU-STACK"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

; MUI Settings
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\orange-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\orange-uninstall.ico"

; Welcome page
!insertmacro MUI_PAGE_WELCOME
; License page
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
; Directory page
!insertmacro MUI_PAGE_DIRECTORY
; Instfiles page
!insertmacro MUI_PAGE_INSTFILES
; Finish page
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Language
!insertmacro MUI_LANGUAGE "English"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "NPU-STACK-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES\NPU-STACK"
ShowInstDetails show
ShowUnInstDetails show

Section "Install"
    SetOutPath "$INSTDIR"
    
    ; Kill existing processes
    nsExec::Exec "taskkill /F /IM npu-stack-desktop.exe" $0
    nsExec::Exec "taskkill /F /IM python.exe" $0
    
    ; Copy app files
    File /r "..\src-tauri\target\release\${PRODUCT_NAME}.exe"
    File /r "..\dist\*.*"
    
    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_NAME}.exe"
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_NAME}.exe"
    
    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    
    ; Registry
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\${PRODUCT_NAME}.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
    nsExec::Exec "taskkill /F /IM ${PRODUCT_NAME}.exe" $0
    
    Delete "$INSTDIR\${PRODUCT_NAME}.exe"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR\dist"
    RMDir "$INSTDIR"
    
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
    
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
SectionEnd
