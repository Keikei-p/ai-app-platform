Option Explicit

Dim shell, fso, home, repo, command, url
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

url = "http://127.0.0.1:8766/"

If IsAivyRunning(url & "healthz") Then
    shell.Run url, 1, False
    WScript.Quit 0
End If

home = shell.ExpandEnvironmentStrings("%USERPROFILE%")
' Prefer the installed folder containing this launcher; never assume the
' original developer's path or overwrite anything in the user workspace.
repo = fso.GetParentFolderName(WScript.ScriptFullName)

' GitHub ZIP downloads have no .git origin, so they cannot self-update.
' Prefer the one-time Git installation if the shortcut lives in a ZIP copy.
If Not fso.FolderExists(repo & "\.git") Then
    If fso.FolderExists(home & "\Aivy-Latest\.git") Then
        repo = home & "\Aivy-Latest"
    ElseIf fso.FolderExists(home & "\Aivy-Latest-Git\.git") Then
        repo = home & "\Aivy-Latest-Git"
    ElseIf fso.FolderExists(home & "\AI-App-Platform-Git\.git") Then
        repo = home & "\AI-App-Platform-Git"
    Else
        MsgBox "このIvyはZIP版なので自動更新できません。" & vbCrLf & _
               "最初に OPEN_AIVY_WEB.bat を1回だけ実行し、" & vbCrLf & _
               "GitHubのリポジトリURLを登録してください。", _
               vbInformation, "Ivy Auto Update"
        WScript.Quit 1
    End If
End If

If Not fso.FileExists(repo & "\AIVY.bat") Then
    repo = home & "\AI-App-Platform-Git"
End If
If Not fso.FileExists(repo & "\AIVY.bat") Then
    repo = home & "\Aivy-Latest"
End If
If Not fso.FileExists(repo & "\AIVY.bat") Then
    repo = home & "\Aivy-Latest-Git"
End If

If Not fso.FileExists(repo & "\AIVY.bat") Then
    MsgBox "Aivyの最新版が見つかりません。" & vbCrLf & _
           "最初に OPEN_AIVY_WEB.bat を1回だけ実行してください。", _
           vbExclamation, "Aivy Web"
    WScript.Quit 1
End If

command = "cmd.exe /d /c cd /d """ & repo & """ && call AIVY.bat web"
shell.Run command, 0, False

Function IsAivyRunning(statusUrl)
    On Error Resume Next
    Dim http
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    ' The lightweight healthz endpoint responds without calculating full status.
    ' Avoid launching a second Ivy process when a busy status API times out.
    http.SetTimeouts 600, 600, 1200, 1200
    http.Open "GET", statusUrl, False
    http.Send
    IsAivyRunning = (Err.Number = 0 And http.Status = 200)
    If IsAivyRunning Then
        IsAivyRunning = (InStr(1, http.ResponseText, """service""", vbTextCompare) > 0 And _
                         InStr(1, http.ResponseText, """aivy""", vbTextCompare) > 0)
    End If
    Err.Clear
    Set http = Nothing
    On Error GoTo 0
End Function
