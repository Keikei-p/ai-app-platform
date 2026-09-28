Option Explicit

Dim shell, fso, home, repo, command, url
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

url = "http://127.0.0.1:8766/"

If IsAivyRunning(url & "api/v1/status") Then
    shell.Run url, 1, False
    WScript.Quit 0
End If

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

Function IsAivyRunning(statusUrl)
    On Error Resume Next
    Dim http
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts 500, 500, 700, 700
    http.Open "GET", statusUrl, False
    http.Send
    IsAivyRunning = (Err.Number = 0 And http.Status = 200)
    Err.Clear
    Set http = Nothing
    On Error GoTo 0
End Function
