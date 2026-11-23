Option Explicit
Dim sh, fso, dir, pyw, script, cmd, candidates, i
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
script = dir & "\hstech_float.py"

candidates = Array( _
  sh.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python312\pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LocalAppData%") & "\Python\pythoncore-3.12-64\pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LocalAppData%") & "\Python\pythoncore-3.14-64\pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python314\pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LocalAppData%") & "\Microsoft\WindowsApps\pythonw.exe" _
)
pyw = ""
For i = 0 To UBound(candidates)
  If fso.FileExists(candidates(i)) Then
    pyw = candidates(i)
    Exit For
  End If
Next
If pyw = "" Then
  On Error Resume Next
  Dim which
  which = sh.Exec("where pythonw").StdOut.ReadAll
  If InStr(1, which, "pythonw", vbTextCompare) > 0 Then
    pyw = Trim(Split(which, vbCrLf)(0))
  End If
  On Error GoTo 0
End If
If pyw = "" Then
  MsgBox "找不到 pythonw.exe，请先安装 Python。", vbExclamation, "盯盘浮窗"
  WScript.Quit 1
End If
cmd = """" & pyw & """ """ & script & """"
sh.Run cmd, 0, False
