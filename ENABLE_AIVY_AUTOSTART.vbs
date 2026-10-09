Option Explicit

' Opt-in only: this script runs when a user explicitly double-clicks it.
' It creates one current-user Startup shortcut; no admin or scheduled task,
' no automatic GitHub publication and no workspace changes.
Dim shell, fso, installDir, launcher, startupDir, linkPath
Dim wscriptExe, linkArgs, link

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
installDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = installDir & "\AIVY_WEB_SILENT.vbs"

If Not fso.FileExists(launcher) Or Not fso.FileExists(installDir & "\AIVY.bat") Then
    MsgBox "Ivyの起動ファイルが見つかりません。インストール先で実行してください。", vbExclamation, "Ivy 自動起動"
    WScript.Quit 1
End If

startupDir = shell.ExpandEnvironmentStrings("%APPDATA%") & "\Microsoft\Windows\Start Menu\Programs\Startup"
If Not fso.FolderExists(startupDir) Then
    MsgBox "WindowsのStartupフォルダーを確認できません。", vbExclamation, "Ivy 自動起動"
    WScript.Quit 1
End If

linkPath = startupDir & "\Ivy Web Autostart.lnk"
wscriptExe = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\wscript.exe"
linkArgs = "//B //Nologo """ & launcher & """"

If fso.FileExists(linkPath) Then
    Set link = shell.CreateShortcut(linkPath)
    If StrComp(link.TargetPath, wscriptExe, vbTextCompare) = 0 And _
       StrComp(link.Arguments, linkArgs, vbTextCompare) = 0 Then
        MsgBox "Ivyのログイン時自動起動は設定済みです。", vbInformation, "Ivy 自動起動"
        WScript.Quit 0
    End If
    MsgBox "同じ名前の既存ショートカットがあるため上書きしません。", vbExclamation, "Ivy 自動起動"
    WScript.Quit 1
End If

Set link = shell.CreateShortcut(linkPath)
link.TargetPath = wscriptExe
link.Arguments = linkArgs
link.WorkingDirectory = installDir
link.Description = "Start Ivy Web after the current user signs in"
link.Save

MsgBox "設定しました。次回Windowsへのサインイン時にIvy Webを起動します。" & vbCrLf & _
       "PCがスリープ中・サインイン前は起動しません。", vbInformation, "Ivy 自動起動"
