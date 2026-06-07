' cscript.exe re_save_excel.vbs "C:\Apps\ExcelForge2\pipelines\Demo_data\Данные для разделения.xlsx"
Set objExcel = CreateObject("Excel.Application")
objExcel.Visible = False  ' важно, чтобы Excel не открывал окно

filepath = WScript.Arguments(0)
If filepath = "" Then
    WScript.Echo "Использование: cscript save_excel.vbs C:\путь\к\файлу.xlsx"
	WScript.Echo "без консоли cscript.exe //nologo save_excel.vbs C:\путь\к\файлу.xlsx"
    WScript.Quit 1
End If

Set objWorkbook = objExcel.Workbooks.Open(filepath)
objWorkbook.Save
objWorkbook.Close
objExcel.Quit

Set objWorkbook = Nothing
Set objExcel = Nothing