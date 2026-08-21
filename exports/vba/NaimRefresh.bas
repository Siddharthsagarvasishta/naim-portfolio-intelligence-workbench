Attribute VB_Name = "NaimRefresh"
Option Explicit

Public Sub RefreshNaimPackage()
    On Error GoTo Failed
    Application.ScreenUpdating = False
    Application.EnableEvents = False

    Dim exportRoot As String
    exportRoot = NaimConfigValue("ExportRoot")
    ImportCsvToTable NaimSafeCsv(exportRoot & "\tableau\data\kpi_snapshot.csv", exportRoot), "tblKpiSnapshot"
    ImportCsvToTable NaimSafeCsv(exportRoot & "\tableau\data\strategy_snapshot.csv", exportRoot), "tblStrategySnapshot"
    ThisWorkbook.RefreshAll
    Application.CalculateFull
    WriteRefreshMetadata "PASS", ""

CleanExit:
    Application.EnableEvents = True
    Application.ScreenUpdating = True
    Exit Sub
Failed:
    WriteRefreshMetadata "FAIL", Err.Description
    MsgBox "nAIM refresh failed: " & Err.Description, vbCritical, "nAIM"
    Resume CleanExit
End Sub

Private Sub ImportCsvToTable(ByVal csvPath As String, ByVal tableName As String)
    Dim target As ListObject, query As QueryTable
    Set target = FindTable(tableName)
    If target Is Nothing Then Err.Raise vbObjectError + 750, "NaimRefresh", "Missing named table: " & tableName
    If Not target.DataBodyRange Is Nothing Then target.DataBodyRange.Delete
    Set query = target.Parent.QueryTables.Add("TEXT;" & csvPath, target.HeaderRowRange.Cells(2, 1))
    With query
        .TextFileParseType = xlDelimited
        .TextFileCommaDelimiter = True
        .TextFilePlatform = 65001
        .AdjustColumnWidth = False
        .Refresh BackgroundQuery:=False
        .Delete
    End With
End Sub

Private Function FindTable(ByVal tableName As String) As ListObject
    Dim sheet As Worksheet, table As ListObject
    For Each sheet In ThisWorkbook.Worksheets
        For Each table In sheet.ListObjects
            If StrComp(table.Name, tableName, vbTextCompare) = 0 Then
                Set FindTable = table
                Exit Function
            End If
        Next table
    Next sheet
End Function

Private Sub WriteRefreshMetadata(ByVal statusText As String, ByVal detailText As String)
    Dim target As Range
    Set target = ThisWorkbook.Names("Naim_Refresh_Log").RefersToRange
    target.Rows(2).Insert Shift:=xlDown
    target.Cells(2, 1).Value = Now
    target.Cells(2, 2).Value = Environ$("Username")
    target.Cells(2, 3).Value = statusText
    target.Cells(2, 4).Value = detailText
End Sub

