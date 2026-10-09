Option Explicit

' Explicit user-invoked opt-out. Only remove the exact Ivy shortcut.
Dim shell, fso, installDir, launcher, startupDir, linkPath
Dim wscriptExe, linkArgs, link

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
installDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = installDir & "\AIVY_WEB_SILENT.vbs"
startupDir = shell.ExpandEnvironmentStrings("%APPDATA%") & "\Microsoft\Windows\Start Menu\Programs\Startup"
linkPath = startupDir & "\Ivy Web Autostart.lnk"
wscriptExe = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\wscript.exe"
linkArgs = "//B //Nologo """ & launcher & """"

If Not fso.FileExists(linkPath) Then
    MsgBox "Ivyの自動起動ショートカットはありません。", vbInformation, "Ivy 自動起動"
    WScript.Quit 0
End If

Set link = shell.CreateShortcut(linkPath)
If StrComp(link.TargetPath, wscriptExe, vbTextCompare) <> 0 Or _
   StrComp(link.Arguments, linkArgs, vbTextCompare) <> 0 Then
    MsgBox "別のショートカットを誤って削除しないため、変更しませんでした。", vbExclamation, "Ivy 自動起動"
    WScript.Quit 1
End If

fso.DeleteFile linkPath, True
MsgBox "Ivyのログイン時自動起動を解除しました。ワークスペースと履歴は削除していません。", vbInformation, "Ivy 自動起動"
