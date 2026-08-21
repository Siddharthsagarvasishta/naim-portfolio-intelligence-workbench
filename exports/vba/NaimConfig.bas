Attribute VB_Name = "NaimConfig"
Option Explicit

Public Function NaimConfigValue(ByVal keyName As String) As String
    Dim cfg As Range, rowIndex As Long
    Set cfg = ThisWorkbook.Names("Naim_Config").RefersToRange
    For rowIndex = 1 To cfg.Rows.Count
        If StrComp(CStr(cfg.Cells(rowIndex, 1).Value2), keyName, vbTextCompare) = 0 Then
            NaimConfigValue = CStr(cfg.Cells(rowIndex, 2).Value2)
            Exit Function
        End If
    Next rowIndex
    Err.Raise vbObjectError + 740, "NaimConfig", "Missing configuration key: " & keyName
End Function

Public Function NaimSafePath(ByVal candidate As String, ByVal allowedRoot As String) As String
    Dim fso As Object, fullCandidate As String, fullRoot As String
    Set fso = CreateObject("Scripting.FileSystemObject")
    fullCandidate = fso.GetAbsolutePathName(candidate)
    fullRoot = fso.GetAbsolutePathName(allowedRoot)
    If Right$(fullRoot, 1) <> Application.PathSeparator Then fullRoot = fullRoot & Application.PathSeparator
    If StrComp(Left$(fullCandidate, Len(fullRoot)), fullRoot, vbTextCompare) <> 0 Then
        Err.Raise vbObjectError + 741, "NaimConfig", "Path is outside the approved export root."
    End If
    NaimSafePath = fullCandidate
End Function

Public Function NaimSafeCsv(ByVal candidate As String, ByVal allowedRoot As String) As String
    Dim safePath As String
    safePath = NaimSafePath(candidate, allowedRoot)
    If LCase$(Right$(safePath, 4)) <> ".csv" Then
        Err.Raise vbObjectError + 742, "NaimConfig", "Only CSV imports are permitted."
    End If
    NaimSafeCsv = safePath
End Function

