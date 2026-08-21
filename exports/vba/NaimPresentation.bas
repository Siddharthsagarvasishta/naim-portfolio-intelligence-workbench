Attribute VB_Name = "NaimPresentation"
Option Explicit

Public Sub CreateApprovedNaimPack()
    Dim ppt As Object, deck As Object, slide As Object
    Dim titleText As String
    titleText = CStr(ThisWorkbook.Names("Naim_Report_Title").RefersToRange.Value2)
    Set ppt = CreateObject("PowerPoint.Application")
    ppt.Visible = True
    Set deck = ppt.Presentations.Add

    Set slide = deck.Slides.Add(1, 1)
    slide.Shapes.Title.TextFrame.TextRange.Text = titleText
    slide.Shapes.Placeholders(2).TextFrame.TextRange.Text = "Synthetic evidence snapshot — human review required"

    AddRangeAsEditableTable deck, "Naim_Executive_Summary", "Executive summary"
    AddRangeAsEditableTable deck, "Naim_KPI_Table", "Portfolio scorecard"
    AddRangeAsEditableTable deck, "Naim_Reconciliation", "Metric reconciliation"

    MsgBox "Draft pack created. Review evidence metadata and save to an approved path.", vbInformation, "nAIM"
End Sub

Private Sub AddRangeAsEditableTable(ByVal deck As Object, ByVal rangeName As String, ByVal slideTitle As String)
    Dim slide As Object, source As Range
    Set source = ThisWorkbook.Names(rangeName).RefersToRange
    Set slide = deck.Slides.Add(deck.Slides.Count + 1, 11)
    slide.Shapes.Title.TextFrame.TextRange.Text = slideTitle
    source.Copy
    slide.Shapes.PasteSpecial DataType:=10
End Sub

