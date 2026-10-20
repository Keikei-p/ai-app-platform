Option Explicit

' Explicit user-invoked opt-out. Only remove the exact Ivy shortcut.
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
startupDir = shell.ExpandEnvironmentStrings("%APPDATA%") & "\Microsoft\Windows\Start Menu\Programs\Startup"
linkPath = startupDir & "\Ivy Web Autostart.lnk"
wscriptExe = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\wscript.exe"
linkArgs = "//B //Nologo """ & launcher & """"

If Not fso.FileExists(linkPath) Then
    MsgBox "Ivy autostart shortcut was not found.", vbInformation, "Ivy Autostart"
    WScript.Quit 0
End If

Set link = shell.CreateShortcut(linkPath)
If StrComp(link.TargetPath, wscriptExe, vbTextCompare) <> 0 Or _
   StrComp(link.Arguments, linkArgs, vbTextCompare) <> 0 Then
    MsgBox "Existing shortcut was not changed because its target differs.", vbExclamation, "Ivy Autostart"
    WScript.Quit 1
End If

fso.DeleteFile linkPath, True
MsgBox "Ivy autostart disabled. Workspace and history remain intact.", vbInformation, "Ivy Autostart"
