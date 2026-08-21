Option Explicit

Dim fso, shell, cfg, sourceRoot, sourceFile, destinationRoot, destinationFolder
Dim sourcePath, destinationPath, logPath, stamp, openAfterCopy
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

If WScript.Arguments.Count <> 1 Then
  WScript.Echo "Usage: cscript copy_latest_export.vbs <approved-config.ini>"
  WScript.Quit 2
End If

Set cfg = ReadConfig(WScript.Arguments(0))
sourceRoot = fso.GetAbsolutePathName(cfg("SourceRoot"))
destinationRoot = fso.GetAbsolutePathName(cfg("DestinationRoot"))
sourceFile = SafeChild(sourceRoot, cfg("SourceFile"))
destinationFolder = SafeChild(destinationRoot, cfg("DestinationFolder"))
logPath = SafeChild(destinationRoot, cfg("LogFile"))
openAfterCopy = LCase(cfg("OpenAfterCopy")) = "true"

If LCase(Right(sourceFile, 5)) <> ".xlsx" Then Fail "Only .xlsx source files are permitted.", logPath
If Not fso.FileExists(sourceFile) Then Fail "Source file does not exist.", logPath
If Not fso.FolderExists(destinationFolder) Then fso.CreateFolder destinationFolder
If Not fso.FolderExists(fso.GetParentFolderName(logPath)) Then fso.CreateFolder fso.GetParentFolderName(logPath)

stamp = Replace(Replace(Replace(CStr(Year(Now)) & Right("0" & Month(Now), 2) & Right("0" & Day(Now), 2) & "_" & Right("0" & Hour(Now), 2) & Right("0" & Minute(Now), 2) & Right("0" & Second(Now), 2), ":", ""), "/", ""), " ", "_")
destinationPath = fso.BuildPath(destinationFolder, "nAIM_Portfolio_Intelligence_Workbench_" & stamp & ".xlsx")
fso.CopyFile sourceFile, destinationPath, False
AppendLog logPath, "PASS|" & destinationPath
If openAfterCopy Then shell.Run """" & destinationPath & """", 1, False
WScript.Echo destinationPath

Function ReadConfig(path)
  Dim dict, stream, line, pos, key, value
  Set dict = CreateObject("Scripting.Dictionary")
  Set stream = fso.OpenTextFile(fso.GetAbsolutePathName(path), 1, False)
  Do Until stream.AtEndOfStream
    line = Trim(stream.ReadLine)
    If Len(line) > 0 And Left(line, 1) <> "#" Then
      pos = InStr(line, "=")
      If pos > 1 Then
        key = Trim(Left(line, pos - 1))
        value = Trim(Mid(line, pos + 1))
        dict(key) = value
      End If
    End If
  Loop
  stream.Close
  Set ReadConfig = dict
End Function

Function SafeChild(root, child)
  Dim full
  If InStr(child, ":") > 0 Or Left(child, 2) = "\\" Then Fail "Child path must be relative.", ""
  full = fso.GetAbsolutePathName(fso.BuildPath(root, child))
  If LCase(Left(full, Len(root))) <> LCase(root) Then Fail "Path escapes approved root.", ""
  SafeChild = full
End Function

Sub AppendLog(path, message)
  Dim stream
  Set stream = fso.OpenTextFile(path, 8, True)
  stream.WriteLine Now & "|" & message
  stream.Close
End Sub

Sub Fail(message, path)
  If Len(path) > 0 Then AppendLog path, "FAIL|" & message
  WScript.Echo message
  WScript.Quit 1
End Sub

