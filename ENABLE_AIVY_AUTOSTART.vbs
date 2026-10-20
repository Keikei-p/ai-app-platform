Option Explicit

' Opt-in only: this script runs when a user explicitly double-clicks it.
' It creates one current-user Startup shortcut; no admin or scheduled task,
' no automatic GitHub publication and no workspace changes.
Dim shell, fso, installDir, launcher, startupDir, linkPath
Dim wscriptExe, linkArgs, link

Set shell = CreateObject("WScript.Shell")
' A safe syntax check must never create or remove startup shortcuts.
If shell.ExpandEnvironmentStrings("%AIVY_VBS_SYNTAX_CHECK%") = "1" Then
    WScript.Quit 0
End If
Set fso = CreateObject("Scripting.FileSystemObject")
installDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = installDir & "\AIVY_WEB_SILENT.vbs"

If Not fso.FileExists(launcher) Or Not fso.FileExists(installDir & "\AIVY.bat") Then
    MsgBox "Ivy launcher missing. Run from the installed folder.", vbExclamation, "Ivy Autostart"
    WScript.Quit 1
End If

startupDir = shell.ExpandEnvironmentStrings("%APPDATA%") & "\Microsoft\Windows\Start Menu\Programs\Startup"
If Not fso.FolderExists(startupDir) Then
    MsgBox "The Windows Startup folder is not available.", vbExclamation, "Ivy Autostart"
    WScript.Quit 1
End If

linkPath = startupDir & "\Ivy Web Autostart.lnk"
wscriptExe = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\wscript.exe"
linkArgs = "//B //Nologo """ & launcher & """"

If fso.FileExists(linkPath) Then
    Set link = shell.CreateShortcut(linkPath)
    If StrComp(link.TargetPath, wscriptExe, vbTextCompare) = 0 And _
       StrComp(link.Arguments, linkArgs, vbTextCompare) = 0 Then
        MsgBox "Ivy autostart is already enabled.", vbInformation, "Ivy Autostart"
        WScript.Quit 0
    End If
    MsgBox "A shortcut with this name exists. It was not overwritten.", vbExclamation, "Ivy Autostart"
    WScript.Quit 1
End If

Set link = shell.CreateShortcut(linkPath)
link.TargetPath = wscriptExe
link.Arguments = linkArgs
link.WorkingDirectory = installDir
link.Description = "Start Ivy Web after the current user signs in"
link.Save

MsgBox "Ivy Web will start at the next Windows sign-in." & vbCrLf & _
       "It does not run while the PC is sleeping or signed out.", vbInformation, "Ivy Autostart"
