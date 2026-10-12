Option Explicit

' Quiet, one-click desktop launcher. No terminal subprocess or scheduled startup.
' Full source tests remain available through CHECK.bat.
Dim shell, fso, repo, command, exitCode
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repo = fso.GetParentFolderName(WScript.ScriptFullName)
If Not fso.FileExists(repo & "\AIVY.bat") Then
    MsgBox "Aivyの起動ファイルが見つかりません。インストール先で開いてください。", _
        vbExclamation, "Aivy Desktop"
    WScript.Quit 1
End If

' Suppress the BAT command window; a real Tk window still opens normally.
' This uses the already-reviewed, safe fast-forward update launcher.
command = "cmd.exe /d /c cd /d """ & repo & """ && call AIVY.bat"
exitCode = shell.Run(command, 0, True)
If exitCode <> 0 Then
    MsgBox "Aivyを起動できませんでした。CHECK.bat または DIAGNOSTICS.bat で原因を確認してください。" & vbCrLf & _
        "既存のプロジェクトと保存データは削除していません。", _
        vbExclamation, "Aivy Desktop"
End If
WScript.Quit exitCode
