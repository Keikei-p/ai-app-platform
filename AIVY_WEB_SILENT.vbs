Option Explicit

Dim shell, fso, home, repo, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

home = shell.ExpandEnvironmentStrings("%USERPROFILE%")
repo = home & "\Aivy-Latest"

If Not fso.FileExists(repo & "\AIVY.bat") Then
    repo = home & "\Aivy-Latest-Git"
End If

If Not fso.FileExists(repo & "\AIVY.bat") Then
    MsgBox "Aivyの最新版が見つかりません。" & vbCrLf & _
           "最初に OPEN_AIVY_WEB.bat を1回だけ実行してください。", _
           vbExclamation, "Aivy Web"
    WScript.Quit 1
End If

command = "cmd.exe /c cd /d """ & repo & """ && call AIVY.bat web"
shell.Run command, 0, False
