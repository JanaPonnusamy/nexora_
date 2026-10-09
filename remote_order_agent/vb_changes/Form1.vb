Imports System.Data.SqlClient
Imports System.Windows.Forms.DataVisualization.Charting
Imports System.IO
Imports System.Text
Imports Excel = Microsoft.Office.Interop.Excel
Imports System.Runtime.InteropServices
Imports Newtonsoft.Json
Imports System.ComponentModel
Imports System.Diagnostics


Public Class Form1
    Private Enum WorkerTask
        SyncTables
        FetchOrderData
    End Enum
    ' Declare global variables
    Private serverName As String
    Private username As String
    Private password As String
    Private database As String
    Private storeName As String
    Private storeCode As String
    Dim selectedOrderId As Double = 0
    Private WithEvents footerTimer As New Timer()

    ' Constants for DataGridView2 (dgvMain) columns
    Private Const COL_ORDER_QTY As Integer = 3
    Private Const COL_PRODUCT_CODE As Integer = 1
    Private isProgrammaticSelection As Boolean = False

    Private oldValue As Integer

    Private lastProductCode As String = ""

    Private dataLoadedFromKeyPress As Boolean = False
    Private _suppressSelectionChange As Boolean = False
    Private _lastSelectedRow As DataGridViewRow = Nothing
    Private _ignoreRowStateChange As Boolean = False
    Private _suppressCellEnter As Boolean = False
    Private _manualCellNavigation As Boolean = False

    Private initialLoadComplete As Boolean = False

    Private tablesToSync As List(Of Tuple(Of String, String))
    Private currentStoreName As String
    Private sourceConnectionString As String

    Dim MinDays As Integer = 15
    Dim MaxDays As Integer = 20
    ' Add at the top (Form-level)
    Private oldQty As Integer = 0
    Private CurrentRowProductCode As String = ""

    Private changingCell As Boolean = False

    Private suppliercode As String = ""

    'M MouseEnter event handler for btnExit
    Private Sub btnExit_MouseEnter(sender As Object, e As EventArgs)
        btnExit.BackColor = System.Drawing.Color.FromArgb(45, 110, 165) ' Darker shade on hover
    End Sub

    ' MouseLeave event handler for btnExit
    Private Sub btnExit_MouseLeave(sender As Object, e As EventArgs)
        btnExit.BackColor = System.Drawing.Color.FromArgb(66, 139, 202) ' Original color when mouse leaves
    End Sub

    Private Async Sub Form1_Shown(sender As Object, e As EventArgs) Handles Me.Shown
        Dim settingsLoaded As Boolean = False

        ' Run DB initialization logic in background
        Await Task.Run(Sub()
                           InitializeConnectionString()
                           ' Check if serverName was loaded
                           If Not String.IsNullOrWhiteSpace(SQL_Connection_Module.serverName) Then
                               settingsLoaded = True
                           End If
                           CheckDatabaseStatusAndConnect()
                       End Sub)

        ' Back on UI thread
        HideAllComponents()
        CustomizeAllDGVs()
        SetAlternatingRowColors(dgvMain)
        AddHandler dgvMain.CellFormatting, AddressOf dgv_CellFormatting
        dgvMain.SelectionMode = DataGridViewSelectionMode.FullRowSelect
        dgvMain.MultiSelect = False

        dgvSupplierList.SelectionMode = DataGridViewSelectionMode.FullRowSelect
        dgvSupplierList.MultiSelect = False

        SetupDgvMainFooter()
        UpdateDgvMainFooter()
        ResizeDgvMainFooterColumns()

        footerTimer.Interval = 1000 ' 1 second for live clock
        footerTimer.Start()
        LocalDB.Checked = True

        ' Check if serverName is loaded
        If settingsLoaded Then
            Me.Text = "Order Management    Connected Server: " & SQL_Connection_Module.serverName
        Else
            Me.Text = "Order Management - Server not initialized"
        End If

        Me.Visible = True
    End Sub

    Private Sub Form1_Load(sender As Object, e As EventArgs) Handles MyBase.Load
        '  InitializeConnectionString()
        ' CheckDatabaseStatusAndConnect()
        ' HideAllComponents()
        'CustomizeAllDGVs() ' Apply the custom styles to all DataGridViews

        'SetAlternatingRowColors(dgvMain)
        Me.Visible = False
        ' Hook up the CellFormatting event
        'AddHandler dgvMain.CellFormatting, AddressOf dgv_CellFormatting
        'dgvMain.SelectionMode = DataGridViewSelectionMode.FullRowSelect
        'dgvMain.MultiSelect = False
        'LocalDB.Checked = True
        AddHandler dgvMain.CellFormatting, AddressOf dgvMain_CellFormatting
    End Sub

    Private Sub HideAllComponents()
        dgvMain.Visible = False
        dgvStoreList.Visible = False
        cboProcess.Visible = False
        txtSupplierSearch.Visible = False
        dgvSupplierList.Visible = False
        dgvOrderDetails.Visible = False
        dgvSalesDetails.Visible = False
        dgvPurchaseDetails.Visible = False
        DGVMapping.Visible = False
        DgvMainFooter.Visible = False
        Chart1.Visible = False
        btnExport.Visible = False
        btnExit.Visible = False
        'GroupBox_MinMaxSetting.Visible = False
        lblProductType.Visible = False
        lblSelectProcess.Visible = False
        lblSupplierName.Visible = False
        lblSelect.Visible = False
        CboSelect.Visible = False
        cboProductType.Visible = False
    End Sub

    ' Example of calling the CustomizeDataGridView method
    Private Sub CustomizeAllDGVs()
        ' Apply the same styling to all DataGridViews
        CustomizeDataGridView(dgvStoreList)
        CustomizeDataGridView(dgvMain)
        CustomizeDataGridView(dgvSalesDetails)
        CustomizeDataGridView(dgvPurchaseDetails)
        CustomizeDataGridView(dgvSupplierList)
        ' Add other DataGridViews here as needed
    End Sub

    ' Reusable function to apply styling to any DataGridView
    Private Sub CustomizeDataGridView(dgv As DataGridView)
        ' Set background color
        dgv.BackgroundColor = Color.WhiteSmoke ' Light color for the background

        ' Set alternating row colors
        dgv.AlternatingRowsDefaultCellStyle.BackColor = Color.LightCyan ' Light blue color for alternate rows
        dgv.AlternatingRowsDefaultCellStyle.ForeColor = Color.Black ' Black text for readability

        ' Set row selection color
        dgv.DefaultCellStyle.SelectionBackColor = Color.LightGreen ' Light green when selecting a row
        dgv.DefaultCellStyle.SelectionForeColor = Color.Black ' Ensure text is readable when selected

        ' Set gridline color (for better definition)
        dgv.GridColor = Color.LightGray

        ' Set header style (make it bold with a different background)
        dgv.ColumnHeadersDefaultCellStyle.Font = New Font("Arial", 10, FontStyle.Bold)
        dgv.ColumnHeadersDefaultCellStyle.BackColor = Color.LightSteelBlue ' Light blue header background
        dgv.ColumnHeadersDefaultCellStyle.ForeColor = Color.Black ' Dark header text for contrast

        ' Adjust row height for better readability
        dgv.RowTemplate.Height = 30
    End Sub

    ' TextChanged event for txtStoreSearch (live search for store names)
    Private Sub txtStoreSearch_TextChanged(sender As Object, e As EventArgs) Handles txtStoreSearch.TextChanged
        If String.IsNullOrWhiteSpace(txtStoreSearch.Text) Then
            dgvStoreList.Visible = False
            Return
        End If

        Try
            Using con As New SqlConnection(destinationConnectionString)
                Dim query As String = "SELECT STORECODE, STORENAME FROM stores WHERE isactive = 1 AND storename LIKE @storename + '%';"
                Using cmd As New SqlCommand(query, con)
                    cmd.Parameters.AddWithValue("@storename", txtStoreSearch.Text.Trim())

                    Dim da As New SqlDataAdapter(cmd)
                    Dim ds As New DataSet()

                    da.Fill(ds, "STORES")

                    dgvStoreList.DataSource = ds.Tables("STORES")
                    dgvStoreList.ReadOnly = True
                    dgvStoreList.AllowUserToAddRows = False
                    dgvStoreList.Visible = True
                    dgvStoreList.Location = New Point(txtStoreSearch.Left, txtStoreSearch.Bottom + 5) ' Position below search box
                End Using
            End Using
        Catch ex As Exception
            MessageBox.Show("Error fetching store data: " & ex.Message, "Database Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    ' KeyDown event for txtStoreSearch (handle Enter, Escape, and Down arrow keys)
    Private Sub txtStoreSearch_KeyDown(sender As Object, e As KeyEventArgs) Handles txtStoreSearch.KeyDown
        If e.KeyCode = Keys.Enter Then
            ' When Enter key is pressed, set focus to dgvStoreList and select the first row
            If dgvStoreList.Rows.Count > 0 Then
                dgvStoreList.Focus()
                dgvStoreList.Rows(0).Selected = True ' Select the first row
            End If
            e.SuppressKeyPress = True ' Prevent the default "ding" sound when Enter is pressed
        ElseIf e.KeyCode = Keys.Escape Then
            ' When Escape key is pressed, hide the DataGridView and clear the search box
            dgvStoreList.Visible = False
            txtStoreSearch.Clear()
            txtStoreSearch.Focus()
        ElseIf e.KeyCode = Keys.Down Then
            ' When Down key is pressed, focus on dgvStoreList
            dgvStoreList.Focus()
            dgvStoreList.Rows(0).Selected = True ' Select the first row
        End If
    End Sub

    Private Sub dgvStoreList_KeyPress(sender As Object, e As KeyPressEventArgs) Handles dgvStoreList.KeyPress
        If e.KeyChar = Convert.ToChar(13) Then ' Check for Enter key
            Dim selectedStoreName As String = dgvStoreList.CurrentRow.Cells(1).Value.ToString()
            txtStoreSearch.Text = selectedStoreName

            ' Define connection string
            Dim conString As String = "Provider=Microsoft.ACE.OLEDB.12.0;Data Source=D:\OrderDotNet\OrderDotNet.accdb"

            ' Using block for automatic disposal of resources
            Using con As New SqlConnection(destinationConnectionString)
                Try
                    con.Open()
                    ' SQL query with parameters to prevent SQL injection
                    Dim sql As String = "SELECT * FROM stores WHERE isactive=1 AND storename LIKE @StoreName;"
                    Using cmd As New SqlCommand(sql, con)
                        ' Use parameters in the query
                        cmd.Parameters.AddWithValue("@StoreName", selectedStoreName)
                        Using da As New SqlDataAdapter(cmd)
                            Dim ds As New DataSet()
                            da.Fill(ds, "stores")

                            If ds.Tables("stores").Rows.Count > 0 Then
                                Dim row As DataRow = ds.Tables("stores").Rows(0)

                                ' Set global variables
                                serverName = row("servername").ToString()
                                username = row("username").ToString()
                                password = row("password").ToString()
                                database = row("database").ToString()
                                storeName = row("storename").ToString()
                                storeCode = row("storecode").ToString()

                                ' Hide the dgvStoreList and show ComboBox and Label
                                dgvStoreList.DataSource = Nothing
                                dgvStoreList.Refresh()
                                dgvStoreList.Visible = False

                                ' Show cboProcess and Label
                                cboProcess.Visible = True
                                lblSelectProcess.Visible = True

                                ' Clear and show ComboBox
                                cboProcess.DataSource = Nothing
                                cboProcess.Items.Clear()
                                cboProcess.Visible = True
                                cboProcess.BringToFront()

                                Dim items As New List(Of String)()

                                If UserSession.UserRole = 1 Then
                                    items.AddRange(New String() {
                                        "Auto Pur UpDate", "Compare Supplier", "Supplier Order Details",
                                        "Pending Order", "Supplier Invoice", "Order Based Supplier Stock",
                                        "Compare Previous Order", "Qty Check", "Supplier Stock", "Process Order",
                                        "Supplier Excel Mapping", "Integrate Order and Purchase", "UnifiedSupplierCode", "Access DB"
                                    })
                                ElseIf UserSession.UserRole = 2 Then
                                    items.AddRange(New String() {
                                        "Auto Pur UpDate", "Compare Supplier", "Supplier Order Details", "Pending Order",
                                        "Supplier Invoice", "Order Based Supplier Stock", "Qty Check"
                                    })
                                End If

                                ' NMV integration: orders for a managed store come from HO via NMVSyncAgent, which also
                                ' owns the data sync. Local order generation and the old direct Sync are not offered.
                                Dim managedStore As Boolean, webExportAllowed As Boolean
                                GetIntegrationFlags(storeName, managedStore, webExportAllowed)
                                If managedStore Then items.Remove("Process Order")
                                Syncbtn.Visible = Not managedStore
                                btnExportJson.Enabled = webExportAllowed
                                Button1.Enabled = webExportAllowed

                                items.Sort()

                                For Each item As String In items
                                    cboProcess.Items.Add(item)
                                Next

                                cboProcess.Focus()

                                Dim qtyCheckIndex As Integer = cboProcess.Items.IndexOf("Qty Check")

                                If qtyCheckIndex >= 0 Then
                                    cboProcess.SelectedIndex = qtyCheckIndex
                                ElseIf cboProcess.Items.Count > 0 Then
                                    cboProcess.SelectedIndex = 0
                                End If
                            Else
                                MessageBox.Show("No active store found with the specified name.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                            End If
                        End Using
                    End Using
                Catch ex As Exception
                    MessageBox.Show("An error occurred: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                End Try
            End Using
        End If
    End Sub



    Private Sub dgvStoreList_KeyDown(sender As Object, e As KeyEventArgs) Handles dgvStoreList.KeyDown
        If e.KeyCode = Keys.Enter Then
            e.Handled = True  '<------ To prevent the default Enter key behavior
        End If
    End Sub

    Public Sub ConfigureDataGridView(dgv As DataGridView)
        If dgv Is Nothing Then
            LogError("DataGridView is not initialized.")
            Return
        End If

        If TypeOf dgv.DataSource Is DataTable Then
            Dim table As DataTable = DirectCast(dgv.DataSource, DataTable)

            ' Setup header appearance
            dgv.Visible = True
            'dgv.Location = New Point(12, 34)
            dgv.AllowUserToAddRows = False
            dgv.RowHeadersVisible = False
            dgv.ColumnHeadersHeight = 30
            dgv.EnableHeadersVisualStyles = False
            dgv.ColumnHeadersDefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter
            dgv.ColumnHeadersDefaultCellStyle.BackColor = Color.LightGray
            dgv.ColumnHeadersDefaultCellStyle.Font = New Font("Segoe UI", 10, FontStyle.Bold)
            dgv.RowTemplate.Height = 25
            ' Dictionary for custom header text
            Dim headerMap As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase) From {
                {"serialno", "#"},
                {"productname", "Product Name"},
                {"suppliername", "Supplier Name"},
                {"orderqty", "Qty"},
                {"stockreceived", "Received Stock"},
                {"freeqty", "Free"},
                {"totalstock", "Stock"},
                {"slsqty", "90 Sls"},
                {"saleunit", "Pack"},
                {"maxsaleqty", "MQty"},
                {"productdesc", "P_Des"},
                {"unitdescription", "Desc"},
                {"mrp", "MRP"},
                {"itemcost", "Cost"},
                {"ptr", "PTR"},
                {"transactiondate", "S_Date"},
                {"lastreceiveddate", "LRD"},
                {"lastsaledate", "LSD"},
                {"grndate", "GRN Date"},
                {"grnno", "GRN No"},
                {"wantedtype", "Wanted"}
            }

            For Each column As DataColumn In table.Columns
                Dim colName As String = column.ColumnName
                Dim colKey As String = colName.ToLowerInvariant()

                ' Set custom or default header text
                If headerMap.ContainsKey(colKey) Then
                    dgv.Columns(colName).HeaderText = headerMap(colKey)
                Else
                    dgv.Columns(colName).HeaderText = System.Globalization.CultureInfo.CurrentCulture.TextInfo.ToTitleCase(colName.ToLower())
                End If

                ' Set column formatting
                Select Case colKey
                    Case "serialno"
                        dgv.Columns(colName).Width = 30
                    Case "productcode"
                        dgv.Columns(colName).Visible = False
                    Case "productname", "suppliername"
                        dgv.Columns(colName).Width = 140
                    Case "mrp", "itemcost", "ptr"
                        dgv.Columns(colName).Width = 50
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                        dgv.Columns(colName).DefaultCellStyle.Format = "N2"
                    Case "orderqty", "stockreceived", "freeqty", "totalstock", "slsqty", "saleunit", "maxsaleqty"
                        dgv.Columns(colName).Width = 50
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                        dgv.Columns(colName).DefaultCellStyle.Format = "N0"
                    Case "productdesc"
                        dgv.Columns(colName).Width = 30
                        dgv.Columns(colName).DefaultCellStyle.Format = "N0"
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                    Case "transactiondate", "grndate", "grnno", "lastreceiveddate", "lastsaledate"
                        dgv.Columns(colName).Width = 60
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                    Case "unitdescription"
                        dgv.Columns(colName).Width = 50
                    Case "wantedtype"
                        dgv.Columns(colName).Width = 100
                    Case Else
                        dgv.Columns(colName).Width = 100
                End Select
            Next
        Else
            LogError("DataSource is not a DataTable or is empty.")
        End If
    End Sub



    Public Sub SetUIState(isVisible As Boolean, controls As Control())
        For Each ctrl As Control In controls
            ctrl.Visible = isVisible
        Next
    End Sub

    Public Sub SetFocus(control As Control)
        If control.Visible Then
            control.Focus()
        End If
    End Sub

    Public Sub ShowMessage(message As String, messageType As MessageBoxIcon)
        MessageBox.Show(message, "Information", MessageBoxButtons.OK, messageType)
    End Sub

    Public Function ExecuteDatabaseQuery(query As String, parameters As List(Of SqlParameter)) As DataTable
        Dim dt As New DataTable()
        Try
            Using conn As New SqlConnection(destinationConnectionString)
                conn.Open()
                Using cmd As New SqlCommand(query, conn)
                    If parameters IsNot Nothing Then
                        cmd.Parameters.AddRange(parameters.ToArray())
                    End If
                    Using da As New SqlDataAdapter(cmd)
                        da.Fill(dt)
                    End Using
                End Using
            End Using
        Catch ex As Exception
            LogError("Error executing query: " & ex.Message)
        End Try
        Return dt
    End Function

    Public Sub LogError(errorMessage As String)
        ' Assuming there's a table called ErrorLog in the database
        Dim query As String = "INSERT INTO ErrorLog (ErrorMessage, Module, DateTime) VALUES (@ErrorMessage, @Module, @DateTime)"
        Dim parameters As New List(Of SqlParameter) From {
            New SqlParameter("@ErrorMessage", errorMessage),
            New SqlParameter("@Module", "YourModuleName"),
            New SqlParameter("@DateTime", DateTime.Now)
        }
        ExecuteDatabaseQuery(query, parameters)
    End Sub

    Private Sub cboProcess_Enter(sender As Object, e As EventArgs) Handles cboProcess.Enter
        HideAll() ' Hide everything when cboProcess is focused
    End Sub

    Private Sub CboSelect_LostFocus(sender As Object, e As EventArgs) Handles CboSelect.LostFocus
        ' ShowOnly(lblSelect, CboSelect)
    End Sub

    Private Sub cboProcess_KeyPress(sender As Object, e As KeyPressEventArgs) Handles cboProcess.KeyPress
        If e.KeyChar = ChrW(Keys.Enter) Then

            ' Ensure cboProcess has a selected item
            If cboProcess.SelectedItem Is Nothing Then
                MessageBox.Show("Please select a valid item from cboProcess.")
                e.Handled = True
                Return
            End If

            ' Get the selected item from cboProcess
            Dim selectedItem As String = cboProcess.SelectedItem.ToString()

            ' Perform actions based on the selected item
            Select Case selectedItem
                Case "Auto Pur UpDate", "Supplier Stock", "Supplier Invoice", "Supplier Order Details", "UnifiedSupplierCode", "Order Based Supplier Stock", "Supplier Excel Mapping"
                    ' For these cases, focus on txtSupplierSearch
                    ShowOnly(lblSupplierName, txtSupplierSearch)
                    lblSupplierName.Location = New Point(480, 12)
                    txtSupplierSearch.Location = New Point(600, 12)

                    btnExport.Visible = True
                    btnExportJson.Visible = True
                    txtSupplierSearch.Focus()

                Case "Pending Order"
                    ShowOnly(lblProductType, cboProductType)
                    ' Populate cboProductType
                    cboProductType.Items.Clear()
                    cboProductType.Items.Add("All")
                    cboProductType.Items.Add("Pharma")
                    cboProductType.Items.Add("Non Pharma")

                    cboProductType.SelectedIndex = 0
                    ShowOnly(lblSupplierName, txtSupplierSearch)
                    ShowDetailsAndChart()
                    txtSupplierSearch.Tag = "Pending Order" ' Store the desired text temporarily
                    lblProductType.Visible = True
                    cboProductType.Visible = True
                    btnExport.Visible = True
                    btnExportJson.Visible = True
                    CboSelect.Visible = False
                    lblSelect.Visible = False
                    dgvSupplierList.Visible = False
                    cboProductType.Focus()

           Case "Process Order"
                    If IsIntegrationManagedStore(storeName) Then
                        MessageBox.Show("Orders for " & storeName & " are generated by HO and delivered automatically." & vbCrLf & "Process Order is not available for this store.", "Process Order", MessageBoxButtons.OK, MessageBoxIcon.Information)
                        e.Handled = True
                        Exit Sub
                    End If
                    ' Show the password form
                    Dim passwordForm As New PasswordPromptForm()

                    If passwordForm.ShowDialog() = DialogResult.OK Then
                        Dim enteredPassword As String = passwordForm.EnteredPassword.Trim()

                        ' Decode the 13-char compact password
                        Dim result As DecodedPasswordResult = PasswordDecoder.DecodeCompactPasscode(enteredPassword)

                        If Not result.Success Then
                            MessageBox.Show("Incorrect or corrupted password. Access denied.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                            Exit Sub
                        End If

                        ' Check if password is only valid for today
                        If result.TargetDate.Date <> Date.Today Then
                            MessageBox.Show("Password expired. Valid only for " & result.TargetDate.ToShortDateString(), "Expired", MessageBoxButtons.OK, MessageBoxIcon.Warning)
                            Exit Sub
                        End If

                        ' Assign decoded values to global variables
                        Dim storeCode As String = result.StoreCode
                        Dim orderNo As Integer = result.OrderNo
                        MinDays = result.MinDays
                        MaxDays = result.MaxDays
                        Dim ordY As Integer = result.OrdY
                        Dim cmpY As Integer = result.CmpY

                        ' Proceed with order processing
                        ProcessOrder()
                        e.Handled = True
                    Else
                        MessageBox.Show("Operation cancelled.", "Cancelled", MessageBoxButtons.OK, MessageBoxIcon.Information)
                    End If


                Case "Compare Supplier"
                    LoadOrderIDSupplier()

                    ' Position dgvSupplierList just below cboProcess
                    dgvSupplierList.Left = cboProcess.Left
                    dgvSupplierList.Top = cboProcess.Bottom + 5
                    dgvSupplierList.Width = cboProcess.Width
                    dgvSupplierList.Height = 200
                    dgvSupplierList.BringToFront()
                    dgvSupplierList.Visible = True
                    dgvSupplierList.Focus()

                    btnExport.Visible = False
                    MessageBox.Show("Compare Supplier action executed. Select an order and press Enter.", "Compare Supplier", MessageBoxButtons.OK, MessageBoxIcon.Information)


                Case "Integrate Order and Purchase"
                    IntegrateOrderAndPurchase(storeName)
                    ConfigureDataGridViewnew(dgvMain)

                    dgvMain.Visible = True

                Case "Compare Previous Order"
                    LoadOrderID(storeName) ' Call your function with the store name
                    PositionDataGridViewBelowComboBox()
                    CustomizeDataGridView(dgvSupplierList)
                    dgvSupplierList.ReadOnly = True
                    dgvSupplierList.AllowUserToAddRows = False

                Case "Access DB"
                    Dim tables As New List(Of String) From {
                              "Products",
                              "Suppliers",
                              "Batches",
                              "ProductSaleInformation",
                              "ProductTrans",
                              "PurchaseTrans",
                              "SaleInformation",
                              "SalesRep",
                              "TAX",
                              "SupplierProductMatch"
                          }
                    AccessDbGenerator.GenerateAccessDB(destinationConnectionString, "D:\Source Data\sync.accdb", tables)
                    MessageBox.Show("Access DB generated successfully!", "Done", MessageBoxButtons.OK, MessageBoxIcon.Information)

                Case "Qty Check"
                    ShowOnly(lblProductType, cboProductType)
                    ' Populate cboProductType
                    cboProductType.Items.Clear()
                    cboProductType.Items.Add("All")
                    cboProductType.Items.Add("Pharma")
                    cboProductType.Items.Add("Non Pharma")
                    cboProductType.SelectedIndex = 0
                    btnExport.Visible = False
                    btnExportJson.Visible = False
                    ' Set focus
                    cboProductType.Focus()
                    ShowDetailsAndChart()
                Case Else
                    ' Default action if no case matches
                    MessageBox.Show("Unknown selection")
            End Select

            ' Prevent the beep sound on Enter key press
            e.Handled = True
        End If
    End Sub

    ' Function to get the most recent order date from the database
    Private Function GetMostRecentOrderDate(storename As String) As DateTime
        ' Initialize the order date to a default (invalid) value
        Dim orderDate As DateTime = DateTime.MinValue

        ' Declare the query to retrieve the most recent order date
        Dim query As String = "SELECT TOP 1 CAST(OrderDateTime AS DATE) AS OrderDate " & _
                              "FROM OrderHeaderDetails " & _
                              "WHERE storename = @storename " & _
                              "AND CAST(OrderDateTime AS DATE) < CAST(GETDATE() AS DATE) " & _
                              "ORDER BY OrderDateTime DESC"

        ' Using SqlConnection to interact with the database
        Using con As New SqlConnection(destinationConnectionString)
            Try
                ' Open the connection
                con.Open()

                ' Using SqlCommand to execute the query
                Using cmd As New SqlCommand(query, con)
                    ' Add the parameter for the storename
                    cmd.Parameters.AddWithValue("@storename", storename)

                    ' Execute the query and get the result
                    Using reader As SqlDataReader = cmd.ExecuteReader()
                        ' If there is a result, read the order date
                        If reader.Read() Then
                            orderDate = reader.GetDateTime(0)
                        End If
                    End Using
                End Using
            Catch ex As Exception
                ' Handle any exceptions (like connection issues or SQL errors)
                MessageBox.Show("An error occurred while retrieving the order date: " & ex.Message)
            End Try
        End Using

        ' Return the order date (it will be DateTime.MinValue if no valid date is found)
        Return orderDate
    End Function

    ' Function to handle "Integrate Order and Purchase" logic
    Private Sub IntegrateOrderAndPurchase(storename As String)
        ' Call the GetMostRecentOrderDate function to retrieve the order date
        Dim orderDate As DateTime = GetMostRecentOrderDate(storename)

        ' Check if a valid order date was retrieved
        If orderDate <> DateTime.MinValue Then
            ' Create the OrderProcess object and pass Form1 (Me) to the constructor
            Dim processor As New OrderProcess(Me) ' Passing the current Form1 instance
            processor.UpdatePurchaseTrans4Order(storename, orderDate)
        Else
            ' Handle the case where no valid order date was found
            MessageBox.Show("No valid order date found for the specified store.")
        End If
    End Sub


    ' In Form1
    Public Sub UpdateDataGridView(dataTable As DataTable)
        dgvMain.DataSource = dataTable
        ' Optional: Call ConfigureDataGridView or any other methods to customize the DataGridView
    End Sub

    Private Sub PositionDataGridViewBelowComboBox()
        ' Get the height of cboprocess (ComboBox) and its location on the form
        Dim comboBoxHeight As Integer = cboProcess.Height
        Dim comboBoxTop As Integer = cboProcess.Top

        ' Set the position of dgvdgvSupplierList (DataGridView)
        ' Position it below cboprocess by setting its Top property
        dgvSupplierList.Top = comboBoxTop + comboBoxHeight + 10 ' 10 is for a small gap between ComboBox and DataGridView
        dgvSupplierList.Left = cboProcess.Left ' Align DataGridView with ComboBox horizontally
        dgvSupplierList.Width = 350 ' Optionally, make the width match the ComboBox's width

        ' Make sure DataGridView3 is visible
        dgvSupplierList.Visible = True
    End Sub

    Private Sub LoadOrderID(storename As String)
        ' Get today and yesterday as Date objects
        Dim todayDate As Date = DateTime.Today
        Dim yesterdayDate As Date = todayDate.AddDays(-1)

        ' Query 1: Fetch records from today and yesterday
        Dim queryTodayYesterday As String = _
            "SELECT DISTINCT storename, orderid, WantedDate " & _
            "FROM OrderManagementBackup " & _
            "WHERE CAST(WantedDate AS DATE) >= @YesterdayDate " & _
            "AND storename = @storename " & _
            "ORDER BY WantedDate DESC"

        ' Query 2: If none, fetch last 5 records
        Dim queryLast5 As String = _
            "SELECT DISTINCT TOP 5 storename, orderid, WantedDate " & _
            "FROM OrderManagementBackup " & _
            "WHERE storename = @storename " & _
            "ORDER BY WantedDate DESC"

        Dim table As New DataTable()
        Dim foundRows As Integer = 0

        Using conn As New SqlConnection(destinationConnectionString)
            conn.Open()

            ' 1. Try to get today and yesterday's records
            Using cmd As New SqlCommand(queryTodayYesterday, conn)
                cmd.CommandTimeout = 180
                cmd.Parameters.AddWithValue("@storename", storename)
                cmd.Parameters.AddWithValue("@YesterdayDate", yesterdayDate) ' Pass as parameter
                Using adapter As New SqlDataAdapter(cmd)
                    adapter.Fill(table)
                    foundRows = table.Rows.Count
                End Using
            End Using

            ' 2. If none, get last 5 records
            If foundRows = 0 Then
                table.Clear()
                Using cmd As New SqlCommand(queryLast5, conn)
                    cmd.CommandTimeout = 180
                    cmd.Parameters.AddWithValue("@storename", storename)
                    Using adapter As New SqlDataAdapter(cmd)
                        adapter.Fill(table)
                    End Using
                End Using
            End If

            conn.Close()
        End Using

        ' Bind to DataGridView and show it
        dgvSupplierList.DataSource = table
        dgvSupplierList.Visible = True
        dgvSupplierList.Focus()
    End Sub

    Private Sub ShowOnly(labelToShow As Label, inputToShow As Control)
        ' Hide all labels
        lblProductType.Visible = False
        lblSelect.Visible = False
        lblSupplierName.Visible = False

        ' Hide all input controls
        cboProductType.Visible = False
        CboSelect.Visible = False
        txtSupplierSearch.Visible = False

        ' Set positions based on control being shown
        If inputToShow Is CboSelect AndAlso labelToShow Is lblSelect Then
            labelToShow.Location = New Point(775, 12)
            inputToShow.Location = New Point(900, 12)
        Else
            labelToShow.Location = New Point(480, 12)
            inputToShow.Location = New Point(600, 12)
        End If

        ' Example condition to check if the controls to show are the supplier ones
        If inputToShow Is txtSupplierSearch AndAlso labelToShow Is lblSupplierName Then
            labelToShow.Location = New Point(775, 12)
            inputToShow.Location = New Point(900, 12)
        End If


        ' Clear input if it's a TextBox
        If TypeOf inputToShow Is TextBox Then
            CType(inputToShow, TextBox).Text = ""
        End If

        ' Show the selected label and input
        labelToShow.Visible = True
        inputToShow.Visible = True
    End Sub


    Private Sub txtSupplierSearch_GotFocus(sender As Object, e As EventArgs) Handles txtSupplierSearch.GotFocus
        If txtSupplierSearch.Tag IsNot Nothing AndAlso txtSupplierSearch.Tag.ToString() = "Pending Order" Then
            txtSupplierSearch.Text = "Pending Order"
            txtSupplierSearch.SelectAll()
            dgvSupplierList.DataSource = Nothing
            suppliercode = Nothing
            txtSupplierSearch.Tag = Nothing ' Clear the tag after use
        End If
    End Sub

    Private Sub HideAll()
        ' Hide all labels
        lblProductType.Visible = False
        lblSelect.Visible = False
        lblSupplierName.Visible = False

        ' Hide all input controls
        cboProductType.Visible = False
        CboSelect.Visible = False
        txtSupplierSearch.Visible = False

        dgvMain.Visible = False
        dgvStoreList.Visible = False
        dgvOrderDetails.Visible = False
        dgvSalesDetails.Visible = False
        dgvPurchaseDetails.Visible = False
        DGVMapping.Visible = False
        Chart1.Visible = False

    End Sub

    Private Sub cboProductType_KeyPress(sender As Object, e As KeyPressEventArgs) Handles cboProductType.KeyPress
        If e.KeyChar = ChrW(Keys.Enter) Then

            If cboProcess.SelectedItem Is Nothing Then
                MessageBox.Show("Process not selected.")
                e.Handled = True
                Return
            End If

            Dim selectedProcess As String = cboProcess.SelectedItem.ToString()

            Select Case selectedProcess
                Case "Pending Order"
                    CboSelect.Visible = False
                    lblSelect.Visible = False
                    lblSupplierName.Visible = True
                   
                    txtSupplierSearch.Focus()

                Case "Qty Check"
                    ' Load and show quantity check data
                    LoadQtyCheckData()
                    dgvMain.Focus()

                    UpdateDgvMainFooter()
                    ResizeDgvMainFooterColumns()
                    DgvMainFooter.Visible = True
                    DgvMainFooter.Refresh()
                Case Else
                    MessageBox.Show("Unhandled process type for cboProductType: " & selectedProcess)
            End Select

            dataLoadedFromKeyPress = True
            e.Handled = True
        End If
    End Sub


    Private Sub cboProductType_Leave(sender As Object, e As EventArgs) Handles cboProductType.Leave
        If Not dataLoadedFromKeyPress Then
            LoadQtyCheckData()
            ' ConfigureQtyCheckDataGridView(dgvMain)
        End If

        If cboProcess.Text = "Pending Order" Then
            lblSelect.Visible = False
            CboSelect.Visible = False
        End If
        dataLoadedFromKeyPress = False ' Reset the flag
        txtSupplierSearch.Focus()
    End Sub


    Private Sub LoadQtyCheckData()
        Try
            ' Set flag to prevent SelectionChanged from firing during data load
            _ignoreRowStateChange = True

            If cboProductType.SelectedItem Is Nothing Then
                MessageBox.Show("Please select a valid item from Product Type.")
                cboProductType.Focus()
                Return
            End If

            Dim selectedValue As String = cboProductType.SelectedItem.ToString()

            Dim query As String
            If selectedValue = "All" Then
                query = "SELECT productcode, productname, orderqty,free, totalstock, saleunit, unitdescription, slsqty, mrp, lastreceiveddate, lastsaledate, maxsaleqty, Transactiondate, wantedtype " &
                        "FROM ordermanagement WHERE qtycheck = 0 AND producttypename IN ('Pharma', 'Non Pharma') AND storename = @storename AND status = 0 ORDER BY productname"
            Else
                query = "SELECT productcode, productname, orderqty,free, totalstock, saleunit, unitdescription, slsqty, mrp, lastreceiveddate, lastsaledate, maxsaleqty, Transactiondate, wantedtype " &
                        "FROM ordermanagement WHERE qtycheck = 0 AND producttypename = @SelectedValue AND storename = @storename AND status = 0 ORDER BY productname"
            End If

            Using conn As New SqlConnection(destinationConnectionString)
                Dim adapter As New SqlDataAdapter(query, conn)
                adapter.SelectCommand.Parameters.AddWithValue("@storename", storeName)
                If selectedValue <> "All" Then
                    adapter.SelectCommand.Parameters.AddWithValue("@SelectedValue", selectedValue)
                End If

                Dim dataSet As New DataSet()
                adapter.Fill(dataSet, "OrderManagement")

                ' Add SerialNo column
                Dim serialCol As New DataColumn("SerialNo", GetType(Integer))
                dataSet.Tables("OrderManagement").Columns.Add(serialCol)

                Dim serial As Integer = 1
                For Each row As DataRow In dataSet.Tables("OrderManagement").Rows
                    row("SerialNo") = serial
                    serial += 1
                Next

                dataSet.Tables("OrderManagement").Columns("SerialNo").SetOrdinal(0)
                dgvMain.DataSource = dataSet.Tables("OrderManagement")
                dgvMain.Refresh()
                Application.DoEvents()
                ConfigureDataGridViewnew(dgvMain)

                ' Populate cboSelect with distinct wantedtype values
                Dim distinctValues = (From row In dataSet.Tables("OrderManagement").AsEnumerable()
                                      Select row.Field(Of String)("wantedtype")).Distinct().OrderBy(Function(x) x).ToList()
                distinctValues.Insert(0, "All")

                If cboProcess.Text <> "Pending Order" Then
                    CboSelect.Items.Clear()
                    CboSelect.Items.AddRange(distinctValues.ToArray())
                    CboSelect.SelectedIndex = 0
                    lblSelect.Visible = True
                    CboSelect.Visible = True
                End If

                dgvMain.Focus()
                ShowDetailsAndChart()
            End Using

        Catch ex As Exception
            Dim logPath As String = "d:\OrderDotNet\Log\QtyCheck Error.txt"
            Dim errorMessage As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - " & ex.ToString()
            System.IO.File.AppendAllText(logPath, errorMessage & Environment.NewLine)

            MessageBox.Show("An error occurred QTY CHECK: " & ex.Message)
        Finally
            _ignoreRowStateChange = False
        End Try
    End Sub



    Private Sub CboSelect_KeyPress(sender As Object, e As KeyPressEventArgs) Handles CboSelect.KeyPress
        If e.KeyChar = ChrW(Keys.Enter) Then
            LoadQtyCheckData_ByCombo() ' Use helper to load and configure
            'ConfigureQtyCheckDataGridView(dgvMain)
            dataLoadedFromKeyPress = True
            dgvMain.Focus()

            e.Handled = True ' Prevent beep
        End If
    End Sub

    Private Sub CboSelect_Leave(sender As Object, e As EventArgs) Handles CboSelect.Leave
        If Not dataLoadedFromKeyPress Then
            LoadQtyCheckData_ByCombo()
            ' ConfigureQtyCheckDataGridView(dgvMain)

        End If
        dataLoadedFromKeyPress = False ' Reset the flag
    End Sub


    Private Sub LoadQtyCheckData_ByCombo()
        Dim sw As New Stopwatch()
        Dim logFile As String = "D:\OrderDotnet\Log\DGVMainloading.log"

        Try
            sw.Start()

            ' Set flag to prevent SelectionChanged from firing during data load
            _ignoreRowStateChange = True

            If cboProductType.SelectedItem Is Nothing Then
                MessageBox.Show("Please select a valid item from Product Type.")
                cboProductType.Focus()
                Return
            End If

            If CboSelect.SelectedItem Is Nothing Then
                MessageBox.Show("Please select a valid item from Wanted Type.")
                CboSelect.Focus()
                Return
            End If

            Dim selectedType As String = cboProductType.SelectedItem.ToString()
            Dim wantedType As String = CboSelect.SelectedItem.ToString()

            Dim query As String = GetQtyCheckQuery(selectedType, wantedType)

            Using conn As New SqlConnection(destinationConnectionString)
                Dim adapter As New SqlDataAdapter(query, conn)
                adapter.SelectCommand.Parameters.AddWithValue("@storename", storeName)

                If query.Contains("@producttypename") Then
                    adapter.SelectCommand.Parameters.AddWithValue("@producttypename", selectedType)
                End If
                If query.Contains("@wantedtype") Then
                    adapter.SelectCommand.Parameters.AddWithValue("@wantedtype", wantedType)
                End If

                Dim ds As New DataSet()
                adapter.Fill(ds, "OrderManagement")

                If Not ds.Tables("OrderManagement").Columns.Contains("SerialNo") Then
                    ds.Tables("OrderManagement").Columns.Add("SerialNo", GetType(Integer))
                End If

                Dim sn As Integer = 1
                For Each row As DataRow In ds.Tables("OrderManagement").Rows
                    row("SerialNo") = sn
                    sn += 1
                Next
                ds.Tables("OrderManagement").Columns("SerialNo").SetOrdinal(0)
                dgvMain.DataSource = ds.Tables("OrderManagement")
                'ConfigureQtyCheckDataGridView(dgvMain)
                ConfigureDataGridViewnew(dgvMain)

            End Using

        Catch ex As Exception
            MessageBox.Show("An error occurred: " & ex.Message)
        Finally
            sw.Stop()
            _ignoreRowStateChange = False

            ' Log the load time
            Try
                Dim logEntry As String = String.Format("{0} - Data loaded in {1} ms", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"), sw.ElapsedMilliseconds)
                File.AppendAllText(logFile, logEntry & Environment.NewLine)
            Catch logEx As Exception
                ' Optional: suppress logging errors
            End Try
        End Try
    End Sub



    Private Function GetQtyCheckQuery(selectedType As String, wantedType As String) As String
        Dim baseQuery As String = "SELECT productcode, productname, orderqty, totalstock,saleunit, unitdescription, slsqty, mrp, lastreceiveddate, lastsaledate, maxsaleqty, Transactiondate, wantedtype " &
                                  "FROM ordermanagement WHERE qtycheck = 0 AND status = 0 AND storename = @storename"

        If selectedType <> "All" Then
            baseQuery &= " AND producttypename = @producttypename"
        End If

        If wantedType <> "All" Then
            baseQuery &= " AND wantedtype = @wantedtype"
        End If

        baseQuery &= " ORDER BY productname"
        Return baseQuery
    End Function

    Public Sub ConfigureQtyCheckDataGridView(dgv As DataGridView)
        If dgv Is Nothing Then
            LogError("DataGridView is not initialized.")
            Return
        End If

        If Not TypeOf dgv.DataSource Is DataTable OrElse dgv.Columns.Count = 0 Then
            LogError("DataSource is not a DataTable or contains no columns.")
            Return
        End If


        ' General appearance settings
        dgv.Visible = True
        dgv.Location = New Point(12, 34)
        dgv.AllowUserToAddRows = False
        dgv.ReadOnly = False
        dgv.SelectionMode = DataGridViewSelectionMode.FullRowSelect
        dgv.MultiSelect = False
        dgv.RowHeadersVisible = False
        dgv.RowTemplate.Height = 20
        dgv.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.None
        dgv.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.None

        ' Header style
        dgv.ColumnHeadersHeight = 50
        dgv.EnableHeadersVisualStyles = False
        dgv.ColumnHeadersDefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter
        dgv.ColumnHeadersDefaultCellStyle.BackColor = Color.LightGray
        dgv.ColumnHeadersDefaultCellStyle.Font = New Font("Segoe UI", 10, FontStyle.Bold)

        ' Selection color
        dgv.DefaultCellStyle.SelectionBackColor = Color.LightSkyBlue
        dgv.DefaultCellStyle.SelectionForeColor = Color.Black

        ' Custom header text map
        Dim headerMap As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase) From {
            {"serialno", "#"},
            {"productname", "Product Name"},
            {"suppliername", "Supplier Name"},
            {"orderqty", "Or Qty"},
            {"stockreceived", "Received Stock"},
            {"freeqty", "Free"},
            {"totalstock", "Stock"},
            {"slsqty", "Sls Qty"},
            {"saleunit", "Pack"},
            {"maxsaleqty", "Max Qty"},
            {"productdesc", "Pro Desc"},
            {"unitdescription", "Desc"},
            {"mrp", "MRP"},
            {"itemcost", "Cost"},
            {"ptr", "PTR"},
            {"transactiondate", "Txn Date"},
            {"lastreceiveddate", "LR Date"},
            {"lastsaledate", "LS Date"},
            {"grndate", "GRN Date"},
            {"grnno", "GRN No"},
            {"wantedtype", "Wanted"}
        }

        ' Configure columns
        Dim table As DataTable = DirectCast(dgv.DataSource, DataTable)

        For Each column As DataColumn In table.Columns
            Dim colName As String = column.ColumnName
            Dim colKey As String = colName.ToLowerInvariant()

            If dgv.Columns.Contains(colName) Then
                ' Header text
                If headerMap.ContainsKey(colKey) Then
                    dgv.Columns(colName).HeaderText = headerMap(colKey)
                Else
                    dgv.Columns(colName).HeaderText = System.Globalization.CultureInfo.CurrentCulture.TextInfo.ToTitleCase(colName.ToLower())
                End If

                ' ReadOnly except OrderQty
                dgv.Columns(colName).ReadOnly = Not colKey.Equals("orderqty")

                ' Formatting and widths
                Select Case colKey
                    Case "serialno"
                        dgv.Columns(colName).Width = 30
                    Case "productcode"
                        dgv.Columns(colName).Visible = False
                    Case "productname", "suppliername"
                        dgv.Columns(colName).Width = 200
                    Case "mrp", "itemcost", "ptr"
                        dgv.Columns(colName).Width = 50
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                        dgv.Columns(colName).DefaultCellStyle.Format = "N2"
                    Case "orderqty", "stockreceived", "freeqty", "totalstock", "slsqty", "saleunit", "maxsaleqty"
                        dgv.Columns(colName).Width = 45
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                        dgv.Columns(colName).DefaultCellStyle.Format = "N0"
                    Case "productdesc"
                        dgv.Columns(colName).Width = 30
                        dgv.Columns(colName).DefaultCellStyle.Format = "N0"
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                    Case "transactiondate", "grndate", "grnno", "lastreceiveddate", "lastsaledate"
                        dgv.Columns(colName).Width = 60
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                    Case "unitdescription"
                        dgv.Columns(colName).Width = 50
                    Case "wantedtype"
                        dgv.Columns(colName).Width = 100
                    Case Else
                        dgv.Columns(colName).Width = 100
                End Select
            End If
        Next

        dgv.CurrentCell = dgv.Rows(0).Cells("OrderQty")
        dgv.BeginInvoke(New MethodInvoker(Sub()
                                              dgv.BeginEdit(True)
                                          End Sub))


        ' Hook CellFormatting handler
        RemoveHandler dgv.CellFormatting, AddressOf dgv_CellFormatting
        AddHandler dgv.CellFormatting, AddressOf dgv_CellFormatting
    End Sub

    Private Async Sub LoadData(productCode As String)
        Dim srcConn As String = GetSourceConnectionString()
        Dim destConn As String = SQL_Connection_Module.destinationConnectionString
        Try
            ' === Chart Data ===
            Dim statsTable As DataTable = Await RetrieveDataForChartAsync(productCode)

            Dim months = statsTable.AsEnumerable().Select(Function(r) r("MonthOfStatistics").ToString()).ToList()
            Dim stockInHand = statsTable.AsEnumerable().Select(Function(r) Convert.ToInt32(r("StockInHand"))).ToList()
            Dim purchaseQty = statsTable.AsEnumerable().Select(Function(r) Convert.ToInt32(r("PurchaseQuantity"))).ToList()
            Dim saleQty = statsTable.AsEnumerable().Select(Function(r) Convert.ToInt32(r("SaleQuantity"))).ToList()
            Dim adjQty = statsTable.AsEnumerable().Select(Function(r) Convert.ToInt32(r("AdjustmentQuantity"))).ToList()

            PlotChart(months, stockInHand, purchaseQty, saleQty, adjQty)
            Chart1.Visible = True
            ' === Purchase Details ===
            Dim purchaseTable = Await RetrieveDataForPurchaseDetailsAsync(productCode)
            BindDGV(dgvPurchaseDetails, purchaseTable)
            ConfigureDataGridViewnew(dgvPurchaseDetails)

            ' === Sales Details ===
            Dim salesTable = Await RetrieveDataForSalesDetailsAsync(productCode)
            BindDGV(dgvSalesDetails, salesTable)
            ConfigureDataGridViewnew(dgvSalesDetails)

            ' === Order Details ===
            Dim orderTable As DataTable = Await RetrieveDataForOrderDetailsAsync(productCode, destConn, storeName)
            BindDGV(dgvOrderDetails, orderTable)
            ConfigureDataGridViewnew(dgvOrderDetails)

        Catch ex As Exception
            MsgBox("Error loading data: " & ex.Message)
        End Try
    End Sub



    Public Async Function RetrieveDataForPurchaseDetailsAsync(selectedProductCode As String) As Task(Of DataTable)
        Dim isLocal As Boolean = LocalDB.Checked
        Dim query As New System.Text.StringBuilder()

        query.AppendLine("SELECT TOP 10")
        query.AppendLine("    pt.stockreceived AS RStock,")
        query.AppendLine("    pt.FreeQty,")
        query.AppendLine("    pt.ProductDiscPercent AS DIS,")
        query.AppendLine("    pt.itemcost,")
        query.AppendLine("    pt.purchaseprice AS ptr,")
        query.AppendLine("    pt.mrp,")
        query.AppendLine("    pt.grndate,")
        query.AppendLine("    s.suppliername")
        query.AppendLine("FROM purchasetrans pt WITH (NOLOCK)")

        If isLocal Then
            query.AppendLine("INNER JOIN Ordersuppliers s WITH (NOLOCK) ON pt.suppliercode = s.suppliercode AND s.StoreName = @StoreName")
        Else
            query.AppendLine("INNER JOIN suppliers s WITH (NOLOCK) ON pt.suppliercode = s.suppliercode")
        End If

        query.AppendLine("WHERE pt.ProductCode = @ProductCode")

        If isLocal Then
            query.AppendLine("AND pt.StoreName = @StoreName")
        End If

        query.AppendLine("ORDER BY pt.grndate DESC")

        Dim dataTable As New DataTable()
        Dim connectionString As String = If(isLocal, destinationConnectionString, GetSourceConnectionString())

        Try
            ' Open connection asynchronously
            Using connection As New SqlConnection(connectionString)
                Using command As New SqlCommand(query.ToString(), connection)
                    command.Parameters.AddWithValue("@ProductCode", selectedProductCode)
                    If isLocal Then
                        command.Parameters.AddWithValue("@StoreName", storeName)
                    End If

                    ' Open connection asynchronously
                    Await connection.OpenAsync()

                    ' Use ExecuteReaderAsync to execute the query asynchronously
                    Using reader As SqlDataReader = Await command.ExecuteReaderAsync()
                        dataTable.Load(reader)
                    End Using
                End Using
            End Using
        Catch ex As Exception
            MessageBox.Show("Error retrieving purchase details: " & ex.Message)
        End Try

        Return dataTable
    End Function


    Public Async Function RetrieveDataForSalesDetailsAsync(selectedProductCode As String) As Task(Of DataTable)
        Dim isLocal As Boolean = LocalDB.Checked
        Dim query As New System.Text.StringBuilder()

        query.AppendLine("SELECT TOP 10")
        query.AppendLine("    SUM(PS.quantity) AS TotalQuantity,")
        query.AppendLine("    s.Billtime AS Bill_Time,")
        query.AppendLine("    sr.Salesmanname,")
        query.AppendLine("    s.CUSTOMERNAME,")
        query.AppendLine("    PS.DiscountPercentage AS dis,")
        query.AppendLine("    PS.Seriesname AS type,")
        query.AppendLine("    PS.mrp,")
        query.AppendLine("    PS.purchaseprice AS ptr,")
        query.AppendLine("    PS.Bnumber")
        query.AppendLine("FROM ProductSaleInformation PS")
        query.AppendLine("INNER JOIN saleinformation s ON PS.BillNumber = s.BillNumber AND PS.TransactionDate = s.BillDate")

        If isLocal Then
            query.AppendLine("    AND s.StoreName = @StoreName")
        End If

        query.AppendLine("INNER JOIN SalesRep sr ON s.DeliverySalesRep = sr.Salesmancode")

        If isLocal Then
            query.AppendLine("    AND sr.StoreName = @StoreName")
        End If

        query.AppendLine("WHERE PS.ProductCode = @ProductCode AND PS.TransactionValidity = 0")

        If isLocal Then
            query.AppendLine("  AND PS.StoreName = @StoreName")
        End If

        query.AppendLine("GROUP BY")
        query.AppendLine("    PS.Bnumber, s.BillTime, s.CUSTOMERNAME,")
        query.AppendLine("    PS.Seriesname, PS.mrp, PS.purchaseprice,")
        query.AppendLine("    PS.Lastadjustmentdate, PS.DiscountPercentage, sr.Salesmanname")
        query.AppendLine("ORDER BY s.BillTime DESC")

        Dim dataTable As New DataTable()
        Dim connectionString As String = If(isLocal, destinationConnectionString, GetSourceConnectionString())

        Try
            Using connection As New SqlConnection(connectionString)
                Using command As New SqlCommand(query.ToString(), connection)
                    command.Parameters.AddWithValue("@ProductCode", selectedProductCode)

                    If isLocal Then
                        command.Parameters.AddWithValue("@StoreName", storeName)
                    End If

                    Await connection.OpenAsync()
                    Using reader As SqlDataReader = Await command.ExecuteReaderAsync()
                        dataTable.Load(reader)
                    End Using
                End Using
            End Using
        Catch ex As Exception
            MessageBox.Show("Error retrieving sales details: " & ex.Message)
        End Try

        Return dataTable
    End Function


    Public Async Function RetrieveDataForOrderDetailsAsync(selectedProductCode As String, connectionString As String, storename As String) As Task(Of DataTable)
        Dim sqlCommand As String = "SELECT TOP 25 Productcode, ProductName, Orqty, OrgOrderQty, saleunit, MRP, remarks, Wanteddate, WantedType, Orsupplier " & _
                                   "FROM OrderManagementBackup " & _
                                   "WHERE Productcode = @ProductCode AND StoreName = @storename " & _
                                   "ORDER BY Wanteddate DESC"

        Dim dataTable As New DataTable()

        Using connection As New SqlConnection(connectionString)
            Using command As New SqlCommand(sqlCommand, connection)
                command.Parameters.AddWithValue("@ProductCode", selectedProductCode)
                command.Parameters.AddWithValue("@storename", storename)

                ' Open connection asynchronously
                Await connection.OpenAsync()

                ' Execute reader asynchronously
                Using reader As SqlDataReader = Await command.ExecuteReaderAsync()
                    dataTable.Load(reader)
                End Using
            End Using
        End Using

        Return dataTable
    End Function


    Private Function RetrieveDataForOrderSummary(selectedProductCode As String, connectionString As String, storename As String) As DataTable
        Dim dataTable As New DataTable()

        Dim query As String = "SELECT productname, TOTALSTOCK, saleunit, lastreceiveddate, lastsaledate, mrp, unitdescription, " &
                              "orderqty, maxsaleqty, TransactionDate, wantedtype, SLSQTY " &
                              "FROM ordermanagement " &
                              "WHERE productcode = @productcode AND StoreName = @StoreName"

        Using connection As New SqlConnection(connectionString)
            Dim adapter As New SqlDataAdapter(query, connection)
            adapter.SelectCommand.Parameters.AddWithValue("@productcode", selectedProductCode)
            adapter.SelectCommand.Parameters.AddWithValue("@StoreName", storename)

            adapter.Fill(dataTable)
        End Using

        Return dataTable
    End Function

    Private Sub UpdateValues(connection As SqlConnection, productCode As String, newQty As Integer, remark As String)
        Try
            Dim updateQuery As String = "UPDATE ordermanagement SET " & _
                                        "orderqty = @OrderQty, " & _
                                        "remarks = @Remark, " & _
                                        "qtycheck = 1 " & _
                                        "WHERE productcode = @ProductCode " & _
                                        "AND storename = @StoreName " & _
                                        "AND status = 0"

            Using updateCommand As New SqlCommand(updateQuery, connection)
                updateCommand.Parameters.Add("@OrderQty", SqlDbType.Int).Value = newQty
                updateCommand.Parameters.Add("@Remark", SqlDbType.NVarChar).Value = remark
                updateCommand.Parameters.Add("@ProductCode", SqlDbType.NVarChar).Value = productCode
                updateCommand.Parameters.Add("@StoreName", SqlDbType.NVarChar).Value = storeName

                updateCommand.ExecuteNonQuery()
            End Using
        Catch ex As Exception
            MessageBox.Show("Error updating values: " & ex.Message)
        End Try
    End Sub

    Private Sub SetAlternatingRowColors(dgv As DataGridView)
        dgv.RowsDefaultCellStyle.BackColor = Color.White
        dgv.AlternatingRowsDefaultCellStyle.BackColor = Color.LightBlue
    End Sub


    Private Function SafeDate(value As Object, Optional format As String = "dd/MM/yy") As String
        If value IsNot DBNull.Value AndAlso IsDate(value) Then
            Return Convert.ToDateTime(value).ToString(format)
        End If
        Return String.Empty
    End Function

    Private Sub PopulateProductDetails(row As DataRow)

    End Sub

    Private Sub BindDGV(ByVal dgv As DataGridView, ByVal data As DataTable)
        dgv.DataSource = Nothing
        dgv.DataSource = data
    End Sub

    '--- Returns source SQL Server connection string
    Private Function GetSourceConnectionString() As String
        Return "Data Source=" & serverName & ";Initial Catalog=" & database & ";User ID=" & username & ";Password=" & password
    End Function

    '--- Returns destination SQL Server connection string
    Private Function GetDestinationConnectionString() As String
        Return SQL_Connection_Module.destinationConnectionString
    End Function

    Private Async Function RetrieveDataForChartAsync(selectedProductCode As String) As Task(Of DataTable)
        Dim sqlQuery As String = ""
        Dim dataTable As New DataTable()

        If LocalDB.Checked Then
            sqlQuery = "SELECT " &
                       "CONVERT(VARCHAR(7), MonthOfStatistics, 120) AS MonthOfStatistics, " &
                       "ISNULL(SaleQuantity, 0) AS SaleQuantity, " &
                       "ISNULL(StockInHand, 0) AS StockInHand, " &
                       "ISNULL(PurchaseQuantity, 0) AS PurchaseQuantity, " &
                       "ISNULL(AdjustmentQuantity, 0) AS AdjustmentQuantity, " &
                       "ProductCode " &
                       "FROM ProductTrans " &
                       "WHERE ProductCode = @ProductCode " &
                       "AND MonthOfStatistics >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 3, 0)" &
                       "AND StoreName = @StoreName " &
                       "ORDER BY MonthOfStatistics"
        ElseIf RemoteDB.Checked Then
            sqlQuery = "SELECT " &
                       "CONVERT(VARCHAR(7), MonthOfStatistics, 120) AS MonthOfStatistics, " &
                       "ISNULL(SaleQuantity, 0) AS SaleQuantity, " &
                       "ISNULL(StockInHand, 0) AS StockInHand, " &
                       "ISNULL(PurchaseQuantity, 0) AS PurchaseQuantity, " &
                       "ISNULL(AdjustmentQuantity, 0) AS AdjustmentQuantity, " &
                       "ProductCode " &
                       "FROM ProductTrans " &
                       "WHERE ProductCode = @ProductCode " &
                       "AND MonthOfStatistics >= DATEADD(MONTH, -3, GETDATE()) " &
                       "ORDER BY MonthOfStatistics"
        Else
            MessageBox.Show("Please select a database type (Local or Remote).", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return Nothing
        End If

        Dim connStr As String = If(LocalDB.Checked, GetDestinationConnectionString(), GetSourceConnectionString())

        Try
            Using conn As New SqlConnection(connStr)
                Using cmd As New SqlCommand(sqlQuery, conn)
                    cmd.Parameters.AddWithValue("@ProductCode", selectedProductCode)
                    If LocalDB.Checked Then
                        cmd.Parameters.AddWithValue("@StoreName", storeName)
                    End If

                    Await conn.OpenAsync()
                    Using reader As SqlDataReader = Await cmd.ExecuteReaderAsync()
                        dataTable.Load(reader)
                    End Using
                End Using
            End Using
        Catch ex As Exception
            Dim errMsg As String = "Error retrieving chart data: " & ex.Message
            MessageBox.Show(errMsg)
            LogErrorFile(errMsg, "RetrieveDataForChartAsync")
        End Try

        Return dataTable
    End Function


    Private Sub PlotChart(months As List(Of String), stockInHand As List(Of Integer), purchaseQuantity As List(Of Integer), saleQuantity As List(Of Integer), adjustmentQuantity As List(Of Integer))
        ClearChart()
        ' Clear existing chart areas and series
        Chart1.Series.Clear()
        Chart1.ChartAreas.Clear()

        ' Add a new chart area
        Dim chartArea As New ChartArea("ChartArea1")
        Chart1.ChartAreas.Add(chartArea)

        ' Set the range and intervals for the X and Y axes
        chartArea.AxisX.Interval = 1
        chartArea.AxisY.Maximum = New List(Of Integer)() From {stockInHand.Max(), purchaseQuantity.Max(), saleQuantity.Max(), adjustmentQuantity.Max()}.Max() * 1.2
        chartArea.AxisX.MajorGrid.Enabled = False
        chartArea.AxisY.MajorGrid.Enabled = False

        ' Check for negative values in all data lists
        If stockInHand.Concat(purchaseQuantity).Concat(saleQuantity).Concat(adjustmentQuantity).Any(Function(value) value < 0) Then
            Dim zeroStripLine As New StripLine() With {
                .IntervalOffset = 0,
                .StripWidth = 0.1,
                .BackColor = Color.Black,
                .Interval = 0,
                .IntervalOffsetType = DateTimeIntervalType.Number
            }
            chartArea.AxisY.StripLines.Add(zeroStripLine)
        End If

        ' Set X-axis labels to be horizontal (no rotation)
        chartArea.AxisX.LabelStyle.Angle = 0 ' Set the angle to 0 for horizontal labels

        ' Set X-axis label formatting
        chartArea.AxisX.LabelStyle.IsStaggered = False ' Don't stagger labels, keep them in one row
        chartArea.AxisX.LabelStyle.Font = New Font("Arial", 10) ' Optional: adjust font size for readability

        ' Add custom labels for each month in the middle of each column
        For i As Integer = 0 To months.Count - 1
            ' Add custom labels at the center of each bar
            chartArea.AxisX.CustomLabels.Add(i - 0.5, i + 2.5, months(i))
        Next

        ' Define series names and corresponding data lists
        Dim seriesInfo As Dictionary(Of String, Tuple(Of List(Of Integer), Color)) = New Dictionary(Of String, Tuple(Of List(Of Integer), Color)) From {
            {"Purchase", Tuple.Create(purchaseQuantity, Color.Blue)},
            {"Sales", Tuple.Create(saleQuantity, Color.DarkGreen)},
            {"Stock", Tuple.Create(stockInHand, Color.Red)},
            {"Adjustment", Tuple.Create(adjustmentQuantity, Color.Purple)}
        }

        ' Add series to the chart
        For Each kvp As KeyValuePair(Of String, Tuple(Of List(Of Integer), Color)) In seriesInfo
            Dim seriesName As String = kvp.Key
            Dim dataList As List(Of Integer) = kvp.Value.Item1
            Dim seriesColor As Color = kvp.Value.Item2

            Dim series As New Series(seriesName) With {
                .ChartType = SeriesChartType.Column,
                .color = seriesColor
            }

            ' Add data points to the series
            For j As Integer = 0 To months.Count - 1
                Dim dataPoint As New DataPoint() With {
                    .AxisLabel = months(j),
                    .YValues = New Double() {dataList(j)},
                    .Label = dataList(j).ToString()
                }
                series.Points.Add(dataPoint)
            Next
            ' Add annotation for product name
            Dim productNameAnnotation As New TextAnnotation()
            productNameAnnotation.Text = "Product: " & dgvMain.CurrentRow.Cells("productname").Value.ToString()
            productNameAnnotation.Font = New Font("Arial", 10, FontStyle.Bold)
            productNameAnnotation.ForeColor = Color.Black
            productNameAnnotation.X = 0.5
            productNameAnnotation.Y = 1.05
            productNameAnnotation.Alignment = ContentAlignment.MiddleCenter
            Chart1.Annotations.Add(productNameAnnotation)
            Chart1.Series.Add(series)
        Next
    End Sub


    Private Sub LogToFile(message As String)
        Dim logPath As String = "D:\OrderDotNet\Log\Chart.txt"
        Try
            Using writer As New System.IO.StreamWriter(logPath, True)
                writer.WriteLine(message)
            End Using
        Catch ex As Exception
            ' Optional: handle log failure
        End Try
    End Sub


    Private Sub HideDetailsAndChart()
        dgvPurchaseDetails.Visible = False
        dgvSalesDetails.Visible = False
        dgvOrderDetails.Visible = False
        Chart1.Visible = False
    End Sub

    Private Sub ShowDetailsAndChart()
        ' Set all the DataGridViews and Chart1 to visible
        dgvPurchaseDetails.Visible = True
        dgvSalesDetails.Visible = True
        dgvOrderDetails.Visible = True
        Chart1.Visible = True
    End Sub

    Private Sub LoadDataGridView2(query As String, parameters As Dictionary(Of String, Object))
        initialLoadComplete = False

        Using connection As New SqlConnection(destinationConnectionString)
            Try
                connection.Open()
                Using command As New SqlCommand(query, connection)
                    ' Add parameters to the command
                    For Each param In parameters
                        command.Parameters.AddWithValue(param.Key, param.Value)
                    Next

                    Dim adapter As New SqlDataAdapter(command)
                    Dim table As New DataTable()
                    adapter.Fill(table)

                    ' Add a new column for serial numbers
                    Dim serialColumn As New DataColumn("SerialNo", GetType(Integer))
                    table.Columns.Add(serialColumn)

                    ' Add serial numbers to the DataTable
                    Dim serialNumber As Integer = 1
                    For Each row As DataRow In table.Rows
                        row("SerialNo") = serialNumber
                        serialNumber += 1
                    Next

                    ' Reorder columns to make SerialNo the first column
                    table.Columns("SerialNo").SetOrdinal(0)

                    ' Bind the DataTable to DGVMain
                    dgvMain.DataSource = table
                    dgvMain.Visible = True

                  

                    ' Load data for the first row if available
                    If dgvMain.Rows.Count > 0 Then
                        Dim firstRowProductCode As String = Convert.ToString(dgvMain.Rows(0).Cells(1).Value)
                        LoadData(firstRowProductCode)
                    End If

                    ' Additional configuration for DGVMain here...
                    ' (Auto-size, column properties, etc.)
                    '  Chart1.Visible = True
                    dgvMain.Visible = True
                    dgvMain.Focus()
                    initialLoadComplete = True
                    ' Call ConfigureDataGridView to set up the grid
                    ConfigureDataGridViewnew(dgvMain)
                End Using
            Catch ex As Exception
                MessageBox.Show("An error occurred: " & ex.Message, "Load Grid", MessageBoxButtons.OK, MessageBoxIcon.Error)
            End Try
        End Using
    End Sub

    Private Sub ClearChart()
        If Chart1 IsNot Nothing Then
            Chart1.Series.Clear()
            Chart1.ChartAreas.Clear()
            Chart1.Annotations.Clear() ' Clear any annotations
            Chart1.Invalidate()
        End If
    End Sub

    Private Sub ShowTotalRecords()
        Dim totalRecords As Integer = dgvMain.Rows.Count
        'LabelTotalRecords.Text = "Total Records: " & totalRecords.ToString()
    End Sub

    Private Sub LogErrorFile(errorMessage As String, Optional functionName As String = "")
        Dim logFilePath As String = "D:\OrderDotNet\Log\Chat.log"
        Try
            Dim fullMessage As String = String.Format("{0} [{1}] - {2}{3}",
                                                      DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                                                      If(functionName <> "", functionName, "UnknownFunction"),
                                                      errorMessage,
                                                      Environment.NewLine)
            File.AppendAllText(logFilePath, fullMessage)
        Catch ex As Exception
            ' Fallback message box if logging fails (e.g., path issue)
            MessageBox.Show("Logging failed: " & ex.Message)
        End Try
    End Sub

    Private Sub dgvMain_CellBeginEdit(sender As Object, e As DataGridViewCellCancelEventArgs) Handles dgvMain.CellBeginEdit
        If e.ColumnIndex <> 3 Then
            e.Cancel = True
        Else
            oldValue = Convert.ToInt32(dgvMain.Rows(e.RowIndex).Cells(e.ColumnIndex).Value)
        End If
    End Sub

    Private Sub dgvMain_CellEndEdit(sender As Object, e As DataGridViewCellEventArgs) Handles dgvMain.CellEndEdit
        If e.ColumnIndex = 3 AndAlso e.RowIndex >= 0 Then
            Dim row As DataGridViewRow = dgvMain.Rows(e.RowIndex)
            Dim rowIndex As Integer = e.RowIndex + 1 ' +1 for 1-based index
            Dim productCode As String = row.Cells("ProductCode").Value.ToString()
            Dim productName As String = row.Cells("ProductName").Value.ToString()
            Dim totalStock As String = row.Cells("TotalStock").Value.ToString()
            Dim newValue As Integer = Convert.ToInt32(row.Cells(e.ColumnIndex).Value)

            Dim remark As String
            If newValue <> oldValue Then
                Dim diff As Integer = newValue - oldValue
                If newValue = 0 Then
                    remark = "Don't Want to Order"
                ElseIf diff > 0 Then
                    remark = "OrderQty Changed " & diff & " Add"
                Else
                    remark = "OrderQty Changed " & Math.Abs(diff) & " Less"
                End If
            Else
                remark = "No Changes in OrderQty"
            End If

            ' Log the change
            LogDailyActivity(String.Format("Row: {0}, ProductCode: {1}, Name: {2}, OrderQty: {3}, Stock: {4}, Remark: {5}",
                                           rowIndex, productCode, productName, newValue, totalStock, remark))

            ' Update database
            UpdateDatabase(productCode, newValue, remark)
        End If
    End Sub


    ' Handle cell value change
    Private Sub HandleCellValueChange(currentCell As DataGridViewCell)
        Try
            Dim oldValue As Integer = Convert.ToInt32(currentCell.Value)
            Dim newValue As Integer
            If Integer.TryParse(currentCell.Value.ToString(), newValue) Then
                currentCell.Value = newValue
                If oldValue = newValue Then
                    Dim productCode As String = dgvMain.Rows(currentCell.RowIndex).Cells(1).Value.ToString()
                    UpdateDatabase(productCode, newValue, "No Changes In OrderQty")
                End If
            End If
        Catch ex As Exception
            MessageBox.Show("Error in HandleCellValueChange: " & ex.Message)
        End Try
    End Sub

    Private Sub dgv_CellFormatting(sender As Object, e As DataGridViewCellFormattingEventArgs)
        Dim dgv = CType(sender, DataGridView)
        If dgv.CurrentCell Is Nothing Then Exit Sub

        Dim isCurrentRow As Boolean = (e.RowIndex = dgv.CurrentCell.RowIndex)
        Dim isCurrentCell As Boolean = isCurrentRow AndAlso (e.ColumnIndex = dgv.CurrentCell.ColumnIndex)
        Dim columnName As String = dgv.Columns(e.ColumnIndex).Name

        If isCurrentCell Then
            If columnName.Equals("OrderQty", StringComparison.OrdinalIgnoreCase) OrElse columnName.Equals("free", StringComparison.OrdinalIgnoreCase) Then
                e.CellStyle.BackColor = Color.Red
            Else
                e.CellStyle.BackColor = Color.LightYellow
            End If
        ElseIf isCurrentRow Then
            e.CellStyle.BackColor = Color.LightGreen
        Else
            e.CellStyle.BackColor = dgv.DefaultCellStyle.BackColor
        End If
    End Sub

    Private Sub ClearProductDetail()
        ' Clear charts or related product detail controls
        ClearChart() ' Already present
        ' Add any label or detail panel reset if needed here
    End Sub

    Private Sub GetProductDetail(productCode As String)
        If String.IsNullOrWhiteSpace(productCode) Then Return

        Try
            ' You can customize this based on how you load data (e.g., to a chart or grid)
            LoadData(productCode) ' Already implemented and called in SelectionChanged
        Catch ex As Exception
            MessageBox.Show("Error loading product details: " & ex.Message)
        End Try
    End Sub

    Private Function ValidateOrderQty(value As String) As Boolean
        Dim qty As Integer
        If Integer.TryParse(value, qty) AndAlso qty >= 0 Then
            Return True
        Else
            MessageBox.Show("Please enter a valid non-negative number for Order Quantity.", "Validation Error", MessageBoxButtons.OK, MessageBoxIcon.Warning)
            Return False
        End If
    End Function

    Private Sub UpdateProductDetails(rowIndex As Integer)
        Dim newQty As Integer = Convert.ToInt32(dgvMain.Rows(rowIndex).Cells("OrderQty").Value)
        Dim productCode As String = dgvMain.Rows(rowIndex).Cells("ProductCode").Value.ToString()
        Dim remark As String = ""

        If newQty = oldQty Then
            remark = "No Changes in OrderQty"
        ElseIf newQty = 0 Then
            remark = "Don't Want to Order"
        ElseIf newQty > oldQty Then
            remark = "OrderQty Changed " & (newQty - oldQty) & " Add"
        Else
            remark = "OrderQty Changed " & (oldQty - newQty) & " Less"
        End If

        UpdateDatabase(productCode, newQty, remark)
    End Sub

    Private Sub dgvMain_CellClick(sender As Object, e As DataGridViewCellEventArgs) Handles dgvMain.CellClick
        ' --- Keep existing OrderQty logic ---
        If e.RowIndex >= 0 AndAlso dgvMain.Columns(e.ColumnIndex).Name = "OrderQty" Then
            Dim cell = dgvMain.Rows(e.RowIndex).Cells(e.ColumnIndex)
            If cell.Value IsNot Nothing Then
                oldQty = Convert.ToInt32(cell.Value)
            End If
        End If
    End Sub

    Private Sub dgvMain_EditingControlShowing(sender As Object, e As DataGridViewEditingControlShowingEventArgs) Handles dgvMain.EditingControlShowing
        Dim currentColumnIndex As Integer = dgvMain.CurrentCell.ColumnIndex

        ' Only allow editing in OrderQty (index 3) and free (index 4)
        If currentColumnIndex <> 3 AndAlso currentColumnIndex <> 4 Then
            Dim textBox As TextBox = TryCast(e.Control, TextBox)
            If textBox IsNot Nothing Then
                textBox.ReadOnly = True
            End If
        Else
            ' Make sure editing is enabled for allowed columns
            Dim textBox As TextBox = TryCast(e.Control, TextBox)
            If textBox IsNot Nothing Then
                textBox.ReadOnly = False
            End If
        End If
    End Sub

    Private Sub dgvMain_SelectionChanged(sender As Object, e As EventArgs) Handles dgvMain.SelectionChanged
        ' Guard against recursion and unwanted changes
        If _suppressSelectionChange OrElse _ignoreRowStateChange OrElse Not initialLoadComplete Then Return

        If dgvMain.Rows.Count = 0 Then Return

        If dgvMain.CurrentCell IsNot Nothing Then
            Dim rowIndex As Integer = dgvMain.CurrentCell.RowIndex
            ' Ensure the row is selected correctly
            SelectOnlyRow(rowIndex)
        End If

        ' Handle data loading (asynchronously)
        dgvMain.BeginInvoke(Sub()
                                Dim currentRow As DataGridViewRow = dgvMain.CurrentRow
                                If currentRow Is Nothing Then Return

                                ' Optional: Clear chart or other UI components
                                ' ClearChart()

                                Dim selectedProductCode As String = Convert.ToString(currentRow.Cells(1).Value)
                                LogKeyEvent("SelectionChanged", selectedProductCode, currentRow.Index)

                                If Not String.IsNullOrEmpty(selectedProductCode) Then
                                    _ignoreRowStateChange = True
                                    Try
                                        ' Only load data if the product code has changed
                                        If selectedProductCode <> lastProductCode Then
                                            lastProductCode = selectedProductCode
                                            LoadData(selectedProductCode)
                                        End If
                                    Catch ex As Exception
                                        MessageBox.Show("Error loading data: " & ex.Message)
                                    Finally
                                        _ignoreRowStateChange = False
                                    End Try
                                End If
                            End Sub)
    End Sub


    Private Sub dgvMain_RowEnter(sender As Object, e As DataGridViewCellEventArgs) Handles dgvMain.RowEnter
        If changingCell Then Return
        changingCell = True

        Try
            ' Skip processing if the selected process is "Supplier Excel Mapping"
            If cboProcess.SelectedItem IsNot Nothing AndAlso cboProcess.SelectedItem.ToString() = "Supplier Excel Mapping" Then
                Return
            End If

            If dgvMain.Rows.Count > 1 Then
                dgvMain.Rows(e.RowIndex).Cells(3).Style.SelectionBackColor = Color.Yellow
                dgvMain.Rows(e.RowIndex).Cells(3).Style.SelectionForeColor = Color.Black

                If (e.RowIndex + 1) Mod 20 = 0 Then
                    dgvMain.FirstDisplayedScrollingRowIndex = e.RowIndex
                End If
            End If

            ' Log current row and cell if applicable
            If dgvMain.CurrentCell IsNot Nothing Then
                LogKeyEvent("RowEnter", Convert.ToString(dgvMain.CurrentCell.Value), e.RowIndex)
            End If

        Catch ex As Exception
            MessageBox.Show("RowEnter error: " & ex.Message)
        Finally
            changingCell = False
        End Try
    End Sub


    Private Sub dgvMain_PreviewKeyDown(sender As Object, e As PreviewKeyDownEventArgs) Handles dgvMain.PreviewKeyDown
        If e.KeyCode = Keys.Enter OrElse e.KeyCode = Keys.Escape Then
            e.IsInputKey = True
        End If
    End Sub

    Private Sub dgvMain_KeyDown(sender As Object, e As KeyEventArgs) Handles dgvMain.KeyDown
        Dim logPath As String = "D:\OrderDotNet\Log\KeyDownEventLog.txt"
        Dim logBuilder As New System.Text.StringBuilder()
        Dim currentCell As DataGridViewCell = dgvMain.CurrentCell
        If currentCell Is Nothing Then Exit Sub ' Line A

        Dim rowIndex As Integer = currentCell.RowIndex
        Dim productCode As String = ""
        Dim currentRow As DataGridViewRow = Nothing


        Try
            ' Line 1
            If rowIndex >= 0 AndAlso rowIndex < dgvMain.Rows.Count Then
                currentRow = dgvMain.Rows(rowIndex)
                If currentRow IsNot Nothing AndAlso currentRow.Cells("ProductCode") IsNot Nothing Then
                    productCode = Convert.ToString(currentRow.Cells("ProductCode").Value)
                End If
            End If

            logBuilder.AppendLine("===== KeyDown Event =====")
            logBuilder.AppendLine("Timestamp: " & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"))
            logBuilder.AppendLine("Key Pressed: " & e.KeyCode.ToString())
            logBuilder.AppendLine("RowIndex: " & rowIndex.ToString())
            logBuilder.AppendLine("ProductCode: " & productCode)
            logBuilder.AppendLine("IsCurrentCellInEditMode: " & dgvMain.IsCurrentCellInEditMode.ToString())

            Select Case e.KeyCode
                Case Keys.Enter
                    e.Handled = True
                    If dgvMain.IsCurrentCellInEditMode Then dgvMain.EndEdit()
                    logBuilder.AppendLine("Action: Enter key - Committing cell and updating database")

                    If currentRow IsNot Nothing AndAlso Not currentRow.IsNewRow Then
                        Dim orderQtyCell As DataGridViewCell = currentRow.Cells("OrderQty")
                        If orderQtyCell IsNot Nothing Then
                            Dim oldStyle = orderQtyCell.Style
                            logBuilder.AppendLine("Old Color: BackColor=" & If(oldStyle.BackColor.IsEmpty, "Empty", oldStyle.BackColor.Name) &
                                                  ", ForeColor=" & If(oldStyle.ForeColor.IsEmpty, "Empty", oldStyle.ForeColor.Name) &
                                                  ", Font=" & If(oldStyle.Font Is Nothing, "Default Font", oldStyle.Font.Name & " " & oldStyle.Font.Size.ToString()))
                        End If

                        UpdateDatabase(productCode)
                        logBuilder.AppendLine("Called UpdateDatabase(productCode)")

                        HandleCellValueChange(currentCell)
                        MoveToNextRow(rowIndex)
                        SelectOnlyRow(rowIndex + 1)


                    End If

                Case Keys.Escape
                    e.Handled = True
                    If dgvMain.IsCurrentCellInEditMode Then dgvMain.EndEdit()
                    currentCell.Value = 0
                    UpdateDatabase(productCode, 0, "Don't want to Order")
                    logBuilder.AppendLine("Action: Escape key - Set value to 0 and updated")

                    HandleCellValueChange(currentCell)
                    MoveToNextRow(rowIndex)
                    SelectOnlyRow(rowIndex + 1)

                Case Keys.Down
                    e.Handled = True
                    logBuilder.AppendLine("Action: Down key - Move to next row")
                    HandleCellValueChange(currentCell)
                    MoveToNextRow(rowIndex)
                    SelectOnlyRow(rowIndex + 1)

                Case Keys.Up
                    e.Handled = True
                    logBuilder.AppendLine("Action: Up key - Move to previous row")
                    HandleCellValueChange(currentCell)
                    MoveToPreviousRow(rowIndex)
                    SelectOnlyRow(rowIndex - 1)

                Case Keys.Delete
                    e.Handled = True
                    logBuilder.AppendLine("Action: Delete key - Deleting current row")
                    If dgvMain.CurrentRow IsNot Nothing Then DeleteCurrentRow()

                Case Keys.Right


                    logBuilder.AppendLine("===== KeyDown Event =====")
                    logBuilder.AppendLine("Timestamp: " & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"))
                    logBuilder.AppendLine("Key Pressed: " & e.KeyCode.ToString())
                    logBuilder.AppendLine("CurrentCell: Row " & currentCell.RowIndex.ToString() & ", Column " & currentCell.ColumnIndex.ToString() & _
                                         " (" & dgvMain.Columns(currentCell.ColumnIndex).Name & ")")
                    logBuilder.AppendLine("CurrentCell Value: " & Convert.ToString(currentCell.Value))
                    logBuilder.AppendLine("IsCurrentCellInEditMode: " & dgvMain.IsCurrentCellInEditMode.ToString())

                    logBuilder.AppendLine("Focused Column: " & dgvMain.Columns(currentCell.ColumnIndex).Name)
                    logBuilder.AppendLine("Column ReadOnly: " & dgvMain.Columns(currentCell.ColumnIndex).ReadOnly.ToString())
                    logBuilder.AppendLine("Is Editable: " & currentCell.ReadOnly.ToString())

                    If dgvMain.Columns(dgvMain.CurrentCell.ColumnIndex).Name <> "free" Then
                        e.Handled = True
                        dgvMain.CurrentCell = currentRow.Cells("free")
                        dgvMain.BeginEdit(True)

                        logBuilder.AppendLine("Action: Right key - Move focus to 'free' column in current row")
                        If currentRow IsNot Nothing AndAlso currentRow.Cells("free") IsNot Nothing Then
                            _manualCellNavigation = True
                            logBuilder.AppendLine("Manually setting CurrentCell to FREE")

                            dgvMain.CurrentCell = currentRow.Cells("free")
                            dgvMain.BeginEdit(True)
                            logBuilder.AppendLine("Moved to 'free' column and began edit mode")
                        Else
                            logBuilder.AppendLine("Could not find 'free' column in current row")
                        End If
                    End If
                    Dim colName As String = dgvMain.Columns(currentCell.ColumnIndex).Name
                    Dim bgColor As Color = currentCell.Style.BackColor
                    If bgColor.IsEmpty Then bgColor = currentCell.OwningColumn.DefaultCellStyle.BackColor
                    If bgColor.IsEmpty Then bgColor = dgvMain.DefaultCellStyle.BackColor

                    logBuilder.AppendLine("Focused Column: " & colName)
                    logBuilder.AppendLine("Column ReadOnly: " & dgvMain.Columns(currentCell.ColumnIndex).ReadOnly.ToString())
                    logBuilder.AppendLine("Is Editable: " & currentCell.ReadOnly.ToString())
                    logBuilder.AppendLine("BackColor: " & ColorTranslator.ToHtml(bgColor))

            End Select

            ' Write final log
            System.IO.File.AppendAllText(logPath, logBuilder.ToString() & Environment.NewLine)
            _manualCellNavigation = False

        Catch ex As Exception
            Dim errorLog As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - Exception: " & ex.ToString()
            System.IO.File.AppendAllText(logPath, errorLog & Environment.NewLine)
            MessageBox.Show("KeyDown Error: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    Private Sub dgvMain_CellMouseDown(sender As Object, e As DataGridViewCellMouseEventArgs) Handles dgvMain.CellMouseDown
        If e.RowIndex >= 0 Then
            dgvMain.CurrentCell = dgvMain.Rows(e.RowIndex).Cells(e.ColumnIndex)
            SelectOnlyRow(e.RowIndex)
        End If
    End Sub

    Private Sub MoveToNextRow(currentRowIndex As Integer)
        If currentRowIndex < dgvMain.Rows.Count - 1 Then
            Dim newRowIndex As Integer = currentRowIndex + 1
            dgvMain.CurrentCell = dgvMain.Rows(newRowIndex).Cells("OrderQty") ' Ensure "OrderQty" column exists
            dgvMain.Rows(newRowIndex).Selected = True
        Else
            ' At the last row
            LogKeyEvent("EndOfRows", dgvMain.Rows(currentRowIndex).Cells("ProductCode").Value.ToString(), currentRowIndex)
        End If
    End Sub


    Private Sub MoveToPreviousRow(currentRowIndex As Integer)
        If currentRowIndex > 0 Then
            Dim newRowIndex As Integer = currentRowIndex - 1
            dgvMain.CurrentCell = dgvMain.Rows(newRowIndex).Cells("OrderQty")
            dgvMain.Rows(newRowIndex).Selected = True
        End If
    End Sub


    Private Sub WriteLog(eventName As String, Optional productCode As String = "", Optional rowIndex As Integer = -1, Optional rowColor As Color? = Nothing)
        Dim logMessage As String = String.Format("{0:yyyy-MM-dd HH:mm:ss} | KeyPress: {1}", DateTime.Now, eventName)
        If productCode <> "" Then logMessage &= String.Format(" | ProductCode: {0}", productCode)
        If rowIndex >= 0 Then logMessage &= String.Format(" | RowIndex: {0}", rowIndex)
        If rowColor.HasValue Then logMessage &= String.Format(" | RowColor: {0}", rowColor.Value.Name)

        ' Specify the log file path
        Dim logFilePath As String = "d:\OrderDotNet\Log\log.txt"

        ' Append log message to the specified log file
        System.IO.File.AppendAllText(logFilePath, logMessage & Environment.NewLine)
    End Sub


    Private Sub LogKeyEvent(keyName As String, productCode As String, rowIndex As Integer)
        Try
            Dim logDir As String = "D:\OrderDotNet\Log"
            Dim logFile As String = Path.Combine(logDir, "productcode.log")

            If Not Directory.Exists(logDir) Then
                Directory.CreateDirectory(logDir)
            End If

            Using sw As StreamWriter = File.AppendText(logFile)
                sw.WriteLine(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " | KeyPress: " & keyName & " | ProductCode: " & productCode & " | RowIndex: " & rowIndex)
            End Using
        Catch logEx As Exception
            ' Optionally handle the logging failure
        End Try
    End Sub

    ' Delete current row
    Private Sub DeleteCurrentRow()
        If dgvMain.CurrentRow IsNot Nothing Then
            dgvMain.Rows.Remove(dgvMain.CurrentRow)
        End If
    End Sub

    Private Sub dgvMain_CurrentCellDirtyStateChanged(sender As Object, e As EventArgs) Handles dgvMain.CurrentCellDirtyStateChanged
        If dgvMain.IsCurrentCellDirty Then
            dgvMain.CommitEdit(DataGridViewDataErrorContexts.Commit)
        End If
    End Sub

    Private Sub dgvMain_DataBindingComplete(sender As Object, e As DataGridViewBindingCompleteEventArgs) Handles dgvMain.DataBindingComplete
        ' Set initial load complete flag to true after data binding is complete
        initialLoadComplete = True
        ShowTotalRecords()
        LogDgvMainFullContents()
    End Sub


    Private Sub UpdateDatabase(productCode As String, newQty As Integer, remark As String)
        Try
            Using connection As New SqlConnection(destinationConnectionString)
                connection.Open()

                ' Check if remarks is NULL for the given productcode, storename, and status = 0
                Dim checkQuery As String = "SELECT remarks FROM ordermanagement WHERE productcode = @ProductCode AND storename = @StoreName AND status = 0"
                Using checkCommand As New SqlCommand(checkQuery, connection)
                    checkCommand.Parameters.Add("@ProductCode", SqlDbType.NVarChar).Value = productCode
                    checkCommand.Parameters.Add("@StoreName", SqlDbType.NVarChar).Value = storeName

                    ' Execute the scalar query to check the remarks
                    Dim remarks As Object = checkCommand.ExecuteScalar()

                    ' Check if remarks is not DBNull.Value
                    If remarks IsNot DBNull.Value AndAlso remarks IsNot Nothing Then
                        ' Retrieve current values
                        Dim currentRemarks As String = remarks.ToString()

                        ' Check if oldvalue = newvalue
                        Dim selectQtyQuery As String = "SELECT orderqty FROM ordermanagement WHERE productcode = @ProductCode AND storename = @StoreName AND status = 0"
                        Using selectQtyCommand As New SqlCommand(selectQtyQuery, connection)
                            selectQtyCommand.Parameters.Add("@ProductCode", SqlDbType.NVarChar).Value = productCode
                            selectQtyCommand.Parameters.Add("@StoreName", SqlDbType.NVarChar).Value = storeName

                            Dim currentOrderQty As Integer = Convert.ToInt32(selectQtyCommand.ExecuteScalar())

                            ' If oldvalue <> newvalue, update values
                            If currentOrderQty <> newQty Then
                                UpdateValues(connection, productCode, newQty, remark)
                            End If
                        End Using
                    Else
                        ' Remarks is NULL or DBNull.Value, update values
                        UpdateValues(connection, productCode, newQty, remark)
                    End If
                End Using
            End Using
        Catch ex As Exception
            MessageBox.Show("Error: " & ex.Message)
        End Try
    End Sub


    Private logPath As String = "D:\OrderDotNet\Log\UpdateDatabaseColorLog.txt"

    ' General method for logging successful event handling
    Private Sub LogEvent(logContent As String, logPath As String)
        Try
            System.IO.File.AppendAllText(logPath, logContent & Environment.NewLine)
        Catch ex As Exception
            MessageBox.Show("Error writing to log: " & ex.Message, "Log Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    ' General method for logging errors
    Private Sub LogError(ex As Exception, logPath As String)
        Dim errorLog As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - Exception: " & ex.ToString()
        Try
            System.IO.File.AppendAllText(logPath, errorLog & Environment.NewLine)
        Catch logEx As Exception
            MessageBox.Show("Error logging exception: " & logEx.Message, "Log Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    Private Sub UpdateDatabase(ByVal productCode As String)
        Dim logPath As String = "D:\OrderDotNet\Log\UpdateDatabaseLog.txt"

        ' Log the entry point of the method
        Dim logBuilder As New System.Text.StringBuilder()
        logBuilder.AppendLine("===== UpdateDatabase Method =====")
        logBuilder.AppendLine("Timestamp: " & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"))
        logBuilder.AppendLine("ProductCode: " & productCode)
        logBuilder.AppendLine("Process: " & cboProcess.Text)
        logBuilder.AppendLine("SupplierSearch: " & txtSupplierSearch.Text)
        logBuilder.AppendLine("SupplierCode: " & suppliercode)
        logBuilder.AppendLine("StoreName: " & storeName)

        If cboProcess.Text = "Qty Check" Then
            logBuilder.AppendLine("Qty Check process detected. Exiting method.")
            System.IO.File.AppendAllText(logPath, logBuilder.ToString() & Environment.NewLine)
            Exit Sub
        End If

        ' SQL Queries
        Dim updateQuery As String = "UPDATE ordermanagement SET orqty = @orqty, orsupplier = @orsupplier, orsuppliercode = @orsuppliercode, status = 1 WHERE productcode = @productcode AND status = 0 AND storename = @storename"
        Dim nullUpdateQuery As String = "UPDATE ordermanagement SET orqty = NULL, orsupplier = NULL, orsuppliercode = NULL, status = 0 WHERE productcode = @productcode AND status = 1 AND storename = @storename"

        Try
            ' Find the corresponding row in dgvMain
            Dim currentRow As DataGridViewRow = dgvMain.Rows.Cast(Of DataGridViewRow)().FirstOrDefault( _
                Function(row) row.Cells("ProductCode").Value IsNot Nothing AndAlso row.Cells("ProductCode").Value.ToString() = productCode)

            If currentRow Is Nothing Then
                logBuilder.AppendLine("ProductCode not found in DataGridView. Exiting method.")
                System.IO.File.AppendAllText(logPath, logBuilder.ToString() & Environment.NewLine)
                Exit Sub
            End If

            ' Log order quantity before update
            Dim orqty As Integer = 0
            If currentRow.Cells("OrderQty").Value IsNot Nothing AndAlso Not IsDBNull(currentRow.Cells("OrderQty").Value) Then
                Integer.TryParse(currentRow.Cells("OrderQty").Value.ToString(), orqty)
            End If
            logBuilder.AppendLine("OrderQty: " & orqty.ToString())

            Using connection As New SqlConnection(destinationConnectionString)
                connection.Open()
                logBuilder.AppendLine("Database connection established.")

                ' Check current status of the product in the database
                Dim currentStatus As Integer = -1
                Using checkCmd As New SqlCommand("SELECT status FROM ordermanagement WHERE productcode = @productcode AND storename = @storename", connection)
                    checkCmd.Parameters.AddWithValue("@productcode", productCode)
                    checkCmd.Parameters.AddWithValue("@storename", storeName)

                    logBuilder.AppendLine("Executing status check query...")
                    Dim result = checkCmd.ExecuteScalar()
                    If result IsNot Nothing AndAlso Not IsDBNull(result) Then
                        Integer.TryParse(result.ToString(), currentStatus)
                    End If
                End Using

                logBuilder.AppendLine("Current Status: " & currentStatus.ToString())

                ' Only proceed if status is 0
                If currentStatus = 0 Then
                    Using updateCmd As New SqlCommand(updateQuery, connection)
                        updateCmd.Parameters.AddWithValue("@orqty", orqty)

                        If cboProcess.Text = "Pending Order" AndAlso txtSupplierSearch.Text = "Pending Order" Then
                            updateCmd.Parameters.AddWithValue("@orsupplier", cboProcess.Text)
                            updateCmd.Parameters.AddWithValue("@orsuppliercode", "pending")
                        Else
                            updateCmd.Parameters.AddWithValue("@orsupplier", txtSupplierSearch.Text)
                            updateCmd.Parameters.AddWithValue("@orsuppliercode", suppliercode)
                        End If

                        updateCmd.Parameters.AddWithValue("@productcode", productCode)
                        updateCmd.Parameters.AddWithValue("@storename", storeName)

                        logBuilder.AppendLine("Executing update query...")
                        Dim rowsAffected As Integer = updateCmd.ExecuteNonQuery()

                        ' Log query execution result
                        logBuilder.AppendLine("Update Executed. Rows Affected: " & rowsAffected.ToString())

                        ' Log the results of the query execution
                        If rowsAffected > 0 Then
                            ' Update visual style if needed
                            dgvMain.BeginInvoke(Sub()
                                                    currentRow.Cells("OrderQty").Style.BackColor = Color.ForestGreen
                                                    currentRow.Cells("OrderQty").Style.ForeColor = Color.ForestGreen
                                                    currentRow.Cells("OrderQty").Style.Font = New Font("Arial", 14, FontStyle.Bold)

                                                    dgvMain.Invalidate()
                                                    dgvMain.Refresh()

                                                    ' Log color change
                                                    logBuilder.AppendLine("Visual Style Updated: OrderQty - BackColor=ForestGreen, ForeColor=BlueViolet, Font=Arial 14, Bold")
                                                End Sub)
                        Else
                            logBuilder.AppendLine("Update failed: No rows affected.")
                            MessageBox.Show("Update failed.")
                        End If
                    End Using


                ElseIf currentStatus = 1 Then
                    ' Reset values to NULL
                    Using command As New SqlCommand(nullUpdateQuery, connection)
                        command.Parameters.AddWithValue("@productcode", productCode)
                        command.Parameters.AddWithValue("@storename", storeName)

                        Dim rowsAffected As Integer = command.ExecuteNonQuery()

                        If rowsAffected > 0 Then
                            ' Remove re-declaration of currentRow here
                            If currentRow IsNot Nothing AndAlso dgvMain.Columns.Contains("OrderQty") AndAlso currentRow.Cells("OrderQty") IsNot Nothing Then
                                currentRow.Cells("OrderQty").Style.BackColor = Color.Red
                                currentRow.Cells("OrderQty").Style.ForeColor = Color.Red
                                currentRow.Cells("OrderQty").Style.Font = New Font("Arial", 10, FontStyle.Bold)
                                dgvMain.Invalidate()
                                dgvMain.Refresh()

                            Else
                                logBuilder.AppendLine("Warning: 'OrderQty' column not found or cell is null.")
                            End If
                        Else
                            MessageBox.Show("Update failed.")
                        End If
                    End Using
                End If
            End Using

            ' Write the full log at the end of successful handling
            System.IO.File.AppendAllText(logPath, logBuilder.ToString() & Environment.NewLine)

        Catch ex As Exception
            ' Log error if exception occurs
            Dim errorLog As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - Exception: " & ex.ToString()
            System.IO.File.AppendAllText(logPath, errorLog & Environment.NewLine)
            MessageBox.Show("Error updating database: " & ex.Message, "Database Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    Private Sub dgvMain_CellEnter(sender As Object, e As DataGridViewCellEventArgs) Handles dgvMain.CellEnter
        If _suppressCellEnter Then Exit Sub

        Try
            Dim colName As String = dgvMain.Columns(e.ColumnIndex).Name
            ' Only force move if it's not one of the editable columns
            If colName <> "OrderQty" AndAlso colName <> "free" Then
                _suppressCellEnter = True
                ' Do NOT override if we're already on free or OrderQty
                If dgvMain.Columns.Contains("OrderQty") Then
                    dgvMain.CurrentCell = dgvMain.Rows(e.RowIndex).Cells("OrderQty")
                End If
            End If
        Catch ex As Exception
            ' Optional log
        Finally
            _suppressCellEnter = False
        End Try
    End Sub

    Public Sub ConfigureDataGridViewnew(dgv As DataGridView,
                                     Optional headerHeight As Integer = 30,
                                     Optional rowHeight As Integer = 22)
        If dgv Is Nothing OrElse Not TypeOf dgv.DataSource Is DataTable Then Return
        Dim table As DataTable = DirectCast(dgv.DataSource, DataTable)

        ' === Appearance Settings ===
        dgv.BackgroundColor = Color.WhiteSmoke
        dgv.AlternatingRowsDefaultCellStyle.BackColor = Color.LightCyan
        dgv.AlternatingRowsDefaultCellStyle.ForeColor = Color.Black
        dgv.DefaultCellStyle.SelectionBackColor = Color.LightGreen
        dgv.DefaultCellStyle.SelectionForeColor = Color.Black
        dgv.GridColor = Color.LightGray
        dgv.ColumnHeadersDefaultCellStyle.BackColor = Color.LightSteelBlue
        dgv.ColumnHeadersDefaultCellStyle.ForeColor = Color.Black
        dgv.ColumnHeadersDefaultCellStyle.Font = New Font("Arial", 10, FontStyle.Bold)

        ' === General Grid Settings ===
        dgv.Visible = True
        dgv.AllowUserToAddRows = False
        dgv.RowHeadersVisible = False
        dgv.EnableHeadersVisualStyles = False
        dgv.ColumnHeadersHeight = headerHeight
        dgv.RowTemplate.Height = rowHeight
        dgv.ColumnHeadersDefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter

        ' === Header Text Mapping (Fixed: Removed duplicate "Free" key) ===
        Dim headerMap As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase) From {
            {"serialno", "#"}, {"productname", "Product Name"}, {"suppliername", "Supplier Name"},
            {"orderqty", "Or Qty"}, {"stockreceived", "Recv_Stock"}, {"freeqty", "Free"}, {"RStock", "RStock"},
            {"totalstock", "Stock"}, {"slsqty", "Sls Qty"}, {"saleunit", "Pack"}, {"maxsaleqty", "Max Qty"},
            {"productdesc", "Pro Desc"}, {"unitdescription", "Desc"}, {"mrp", "MRP"}, {"itemcost", "Cost"},
            {"ptr", "PTR"}, {"transactiondate", "Txn Date"}, {"lastreceiveddate", "LR Date"}, {"free", "Free"},
            {"lastsaledate", "LS Date"}, {"grndate", "GRN Date"}, {"grnno", "GRN No"}, {"wantedtype", "Wanted"},
            {"wanteddate", "Wanted Date"}, {"orqty", "Or Qty"}, {"orgorderqty", "Org Order Qty"},
            {"orsupplier", "Or Supplier"}, {"totalquantity", "Qty"}, {"bill_time", "Bill Time"},
            {"salesmanname", "Salesman"}, {"customername", "Customer"}, {"type", "Type"},
            {"dis", "Dis"}, {"bnumber", "Bill No"}, {"remarks", "Remarks"}, {"Recv_stk", "Rev Stk"},
            {"S_Stock", "S_Stock"}, {"sch", "Sch"}, {"Minqty", "MinQty"},
            {"SupplierProductCode", "Supplier Product Code"},
            {"SupplierProductName", "Supplier Product Name"}
        }

        ' === Column Configuration ===
        For Each column As DataColumn In table.Columns
            Dim colName As String = column.ColumnName
            Dim colKey As String = colName.ToLowerInvariant()

            If dgv.Columns.Contains(colName) Then
                ' Set header text from dictionary or default
                If headerMap.ContainsKey(colKey) Then
                    dgv.Columns(colName).HeaderText = headerMap(colKey)
                Else
                    dgv.Columns(colName).HeaderText = System.Globalization.CultureInfo.CurrentCulture.TextInfo.ToTitleCase(colKey)
                End If

                ' === Column formatting logic (Fixed: Added cases for new columns) ===
                Select Case colKey
                    Case "serialno", "type"
                        dgv.Columns(colName).Width = 30
                    Case "productcode", "SupplierProductCode"  ' Fixed: Added new column
                        dgv.Columns(colName).Visible = False
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter
                    Case "productname", "suppliername", "orsupplier", "SupplierProductName"  ' Fixed: Added new column
                        dgv.Columns(colName).Width = 200
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleLeft
                    Case "customername", "salesmanname"
                        dgv.Columns(colName).Width = 100
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleLeft
                    Case "mrp", "itemcost", "ptr"
                        dgv.Columns(colName).Width = 50
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                        dgv.Columns(colName).DefaultCellStyle.Format = "N2"
                    Case "totalstock", "orderqty", "stockreceived", "slsqty", "saleunit", "maxsaleqty", "orqty", "orgorderqty", "totalquantity", "free", "S_Stock", "Sch", "Minqty"
                        dgv.Columns(colName).Width = 40
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter
                        dgv.Columns(colName).DefaultCellStyle.Format = "N0"
                    Case "productdesc", "dis", "freeqty", "RStock"
                        dgv.Columns(colName).Width = 40
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                        dgv.Columns(colName).DefaultCellStyle.Format = "N0"
                    Case "wantedtype"
                        dgv.Columns(colName).Width = 80
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                    Case "bill_time", "wanteddate"
                        dgv.Columns(colName).Width = 100
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter
                    Case "transactiondate", "grndate", "lastreceiveddate", "lastsaledate"
                        dgv.Columns(colName).Width = 70
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter
                    Case "bnumber", "grnno"
                        dgv.Columns(colName).Width = 40
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter
                    Case "remarks"
                        dgv.Columns(colName).Width = 150
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleLeft
                    Case Else
                        dgv.Columns(colName).Width = 40
                        dgv.Columns(colName).DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleLeft
                End Select
            End If
        Next

    End Sub

    Private Sub dgvSupplierList_KeyDown(sender As Object, e As KeyEventArgs) Handles dgvSupplierList.KeyDown
        If e.KeyCode = Keys.Enter Then
            e.Handled = True

            If cboProcess.SelectedItem Is Nothing Then Exit Sub
            If cboProcess.SelectedItem.ToString() <> "Compare Supplier" Then Exit Sub
            If dgvSupplierList.CurrentRow Is Nothing Then Exit Sub

            Dim selectedRow As DataGridViewRow = dgvSupplierList.CurrentRow

            Dim orderIdText As String = selectedRow.Cells("orderid").Value.ToString().Trim()
            If Not Double.TryParse(orderIdText, selectedOrderId) Then
                MessageBox.Show("Invalid Order ID", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                Exit Sub
            End If

            Dim selectedStoreName As String = txtStoreSearch.Text.Trim()
            If String.IsNullOrWhiteSpace(selectedStoreName) Then
                MessageBox.Show("Store name is required", "Missing Input", MessageBoxButtons.OK, MessageBoxIcon.Warning)
                Exit Sub
            End If

            ' ✅ Load OrSupplier list
            LoadDistinctOrSuppliers(selectedStoreName, selectedOrderId)
            ' After LoadDistinctOrSuppliers(selectedStoreName, selectedOrderId)
            If dgvSupplierList.CurrentRow IsNot Nothing Then
                Dim wantedDateText As String = ""

                If dgvSupplierList.CurrentRow.Cells("orderid").Value IsNot DBNull.Value Then
                    orderIdText = dgvSupplierList.CurrentRow.Cells("orderid").Value.ToString()
                End If

                If dgvSupplierList.CurrentRow.Cells("WantedDate").Value IsNot DBNull.Value Then
                    wantedDateText = Convert.ToDateTime(dgvSupplierList.CurrentRow.Cells("WantedDate").Value).ToString("yyyy-MM-dd")
                End If

                ' Clear previous content if needed
                DgvMainFooter.Rows.Clear()

                ' Add one row with both values
                DgvMainFooter.Rows.Add("Order ID: " & orderIdText, "Wanted Date: " & wantedDateText)

                DgvMainFooter.Visible = True
            End If

            dgvSupplierList.Visible = False
            dgvSupplierList.DataSource = Nothing
            dgvSupplierList.Refresh()
        ElseIf e.KeyCode = Keys.Down Then
            If dgvSupplierList.CurrentRow IsNot Nothing Then
                dgvSupplierList.ClearSelection()
                dgvSupplierList.Rows(dgvSupplierList.CurrentRow.Index).Selected = True
            End If
        End If
    End Sub


    Private Sub dgvSupplierList_CellClick(sender As Object, e As DataGridViewCellEventArgs) Handles dgvSupplierList.CellClick
        If e.RowIndex >= 0 Then
            dgvSupplierList.CurrentCell = dgvSupplierList.Rows(e.RowIndex).Cells(0)
            MessageBox.Show(dgvSupplierList.RowCount)
        End If
    End Sub

    Private Sub dgvSupplierList_KeyPress(sender As Object, e As KeyPressEventArgs) Handles dgvSupplierList.KeyPress
        If e.KeyChar = ChrW(Keys.Enter) Then
            suppliercode = ""
            initialLoadComplete = False
            ' selectedOrderId = 0
            If cboProcess.SelectedItem Is Nothing Then
                MessageBox.Show("Please select a valid process option.", "Process Required", MessageBoxButtons.OK, MessageBoxIcon.Warning)
                Exit Sub
            End If

            If dgvSupplierList.CurrentRow Is Nothing Then
                MessageBox.Show("No row selected.", "Selection Error", MessageBoxButtons.OK, MessageBoxIcon.Warning)
                Exit Sub
            End If

            If cboProcess.SelectedItem <> "Compare Previous Order" Then
                suppliercode = dgvSupplierList.CurrentRow.Cells(0).Value.ToString()
                Dim supplierName As String = dgvSupplierList.CurrentRow.Cells(1).Value.ToString()

                txtSupplierSearch.Text = supplierName
                dgvSupplierList.DataSource = Nothing
                dgvSupplierList.Refresh()
                dgvSupplierList.Visible = False

            End If

            Dim selectedProcess As String = cboProcess.SelectedItem.ToString()

            Select Case selectedProcess
                Case "Auto Pur UpDate"
                    LoadDataForSupplier(suppliercode)
                    UpdateDgvMainFooter()
                    ResizeDgvMainFooterColumns()
                    DgvMainFooter.Visible = True
                    DgvMainFooter.Refresh()

                Case "Compare Previous Order"
                    Dim orderId As Double

                    If dgvSupplierList.CurrentRow IsNot Nothing AndAlso
                          dgvSupplierList.CurrentRow.Cells.Count > 1 AndAlso
                          Not IsDBNull(dgvSupplierList.CurrentRow.Cells(1).Value) AndAlso
                          Not String.IsNullOrWhiteSpace(dgvSupplierList.CurrentRow.Cells(1).Value.ToString()) Then


                        If Double.TryParse(dgvSupplierList.CurrentRow.Cells(1).Value.ToString(), orderId) Then
                            CompareOrderManagement(orderId)
                            dgvSupplierList.Visible = False
                        Else
                            MessageBox.Show("Order ID is not a valid number.", "Conversion Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                        End If
                    Else
                        MessageBox.Show("No order selected or Order ID is missing.", "Selection Error", MessageBoxButtons.OK, MessageBoxIcon.Warning)
                    End If

                Case "Order Based Supplier Stock"
                    LoadDataForSupplierStock(suppliercode)
                    UpdateDgvMainFooter()
                    ConfigureDataGridViewnew(dgvMain)
                    ResizeDgvMainFooterColumns()
                    DgvMainFooter.Visible = True
                    DgvMainFooter.Refresh()

                Case "Pending Order"
                    HandlePendingOrder()
                    UpdateDgvMainFooter()
                    ResizeDgvMainFooterColumns()
                    DgvMainFooter.Visible = True
                    DgvMainFooter.Refresh()

                Case "Qty Check"
                    ' Optional logic
                    UpdateDgvMainFooter()
                    ResizeDgvMainFooterColumns()
                    DgvMainFooter.Visible = True
                    DgvMainFooter.Refresh()
                Case "Supplier Excel Mapping"
                    If String.IsNullOrEmpty(suppliercode) Then
                        MessageBox.Show("Supplier code is empty. Please select a valid supplier.", "Invalid Supplier", MessageBoxButtons.OK, MessageBoxIcon.Error)
                        txtSupplierSearch.Focus()
                        Exit Sub
                    End If
                    dgvSupplierList.Visible = False
                    Call LoadExcelAndPrepareMapping()

                Case "Supplier Invoice"
                    ProcessExcelFilesAndExportInvnoWise()

                Case "Supplier Order Details"
                    FetchSupplierOrderDetails()

                Case "Supplier Stock"
                    dgvSupplierList.SelectionMode = DataGridViewSelectionMode.FullRowSelect
                    dgvSupplierList.MultiSelect = False

                    If String.IsNullOrEmpty(suppliercode) Then
                        MessageBox.Show("Supplier code is empty. Please select a valid supplier.", "Invalid Supplier", MessageBoxButtons.OK, MessageBoxIcon.Error)
                        txtSupplierSearch.Focus()
                        Exit Sub
                    End If
                    ImportSupplierStockAndInsertToDatabase()

               Case "Compare Supplier"
                    ' Step 1: Load top 10 orders and exit
                    LoadOrderIDSupplier()
                    btnExport.Visible = False
                    btnExportJson.Visible = False
                    MessageBox.Show("Now select an order from the list.", "Next Step", MessageBoxButtons.OK, MessageBoxIcon.Information)
                    Exit Select

                Case "UnifiedSupplierCode"
                    ' Handle logic for unified supplier code if needed

                Case Else
                    MessageBox.Show("Unhandled process: " & selectedProcess, "Unknown Option", MessageBoxButtons.OK, MessageBoxIcon.Information)
            End Select

            If dgvMain.CurrentCell Is Nothing Then
                FocusOrderQtyCell()
            End If

            If selectedProcess <> "Compare Supplier" Then
                dgvSupplierList.DataSource = Nothing
                dgvSupplierList.Refresh()
                dgvSupplierList.Visible = False
            End If


        ElseIf e.KeyChar = ChrW(Keys.Escape) Then
            txtSupplierSearch.Clear()
            dgvSupplierList.DataSource = Nothing
            dgvSupplierList.Refresh()
            dgvSupplierList.Visible = False
        End If
    End Sub

    Private Sub FocusOrderQtyCell()
        If dgvMain.Rows.Count > 0 AndAlso IsColumnExists(dgvMain, "OrderQty") Then
            Dim targetRow As DataGridViewRow = dgvMain.Rows(0)
            Dim orderQtyCell As DataGridViewCell = targetRow.Cells("OrderQty")

            dgvMain.ClearSelection()
            dgvMain.CurrentCell = orderQtyCell
            orderQtyCell.Selected = True
            dgvMain.Focus()
        End If
    End Sub


    ' Utility method to check if a column exists
    Private Function IsColumnExists(grid As DataGridView, columnName As String) As Boolean
        Return grid.Columns.Contains(columnName)
    End Function

    Private Sub LoadExcelAndPrepareMapping()
        Dim openFileDialog As New OpenFileDialog()
        openFileDialog.Filter = "Excel Files|*.xls;*.xlsx;*.xlsm"
        openFileDialog.Title = "Select Excel File to Map Columns"

        If openFileDialog.ShowDialog() = DialogResult.OK Then
            Try
                Dim filePath As String = openFileDialog.FileName
                Dim dtExcel As DataTable = ReadExcelToDataTable(filePath)

                If dtExcel IsNot Nothing AndAlso dtExcel.Columns.Count > 0 Then
                    LoadExcelHeadersToDGVMapping(dtExcel)
                    LoadMappingGrid(dtExcel)
                Else
                    MessageBox.Show("The selected Excel file contains no columns.", "Empty File", MessageBoxButtons.OK, MessageBoxIcon.Warning)
                End If
            Catch ex As Exception
                MessageBox.Show("Failed to read Excel file. Error: " & ex.Message, "File Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            End Try
        End If
    End Sub


    Private Sub LoadExcelHeadersToDGVMapping(dt As DataTable)
        DGVMapping.Columns.Clear()
        DGVMapping.Rows.Clear()

        DGVMapping.Columns.Add("HeaderName", "Excel Column Header")

        For Each col As DataColumn In dt.Columns
            DGVMapping.Rows.Add(col.ColumnName)
        Next
        DGVMapping.Refresh()

        DGVMapping.Visible = True

    End Sub


    Private Function ReadExcelToDataTable(filePath As String) As DataTable
        Dim dt As New DataTable()
        Dim connStr As String = "Provider=Microsoft.ACE.OLEDB.12.0;Data Source=" & filePath & ";Extended Properties='Excel 12.0 Xml;HDR=YES;'"

        Dim conn As New OleDb.OleDbConnection(connStr)
        Try
            conn.Open()
            Dim dtSchema As DataTable = conn.GetOleDbSchemaTable(OleDb.OleDbSchemaGuid.Tables, Nothing)
            Dim sheetName As String = dtSchema.Rows(0)("TABLE_NAME").ToString()

            Dim cmd As New OleDb.OleDbCommand("SELECT * FROM [" & sheetName & "]", conn)
            Dim adapter As New OleDb.OleDbDataAdapter(cmd)
            adapter.Fill(dt)
        Catch ex As Exception
            MessageBox.Show("Error reading Excel: " & ex.Message, "Excel Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        Finally
            If conn.State = ConnectionState.Open Then conn.Close()
        End Try

        Return dt
    End Function

    Private Sub ImportSupplierStockAndInsertToDatabase()
        Dim openFileDialog As New OpenFileDialog()
        openFileDialog.Filter = "Excel Files|*.xlsx;*.xls"
        openFileDialog.Title = "Select an Excel File"

        If openFileDialog.ShowDialog() = DialogResult.OK Then
            Dim filePath As String = openFileDialog.FileName
            Dim dt As DataTable = Nothing
            Dim logPath As String = "D:\OrderDotNet\Log\ExcelImport.txt"
            Dim logBuilder As New System.Text.StringBuilder()
            logBuilder.AppendLine("[" & DateTime.Now.ToString() & "] File: " & filePath)

            Try
                dt = ReadExcelFileUsingInterop(filePath)

                ' Log Excel headers
                Try
                    Dim headers As String = String.Join(", ", dt.Columns.Cast(Of DataColumn).Select(Function(c) c.ColumnName))
                    System.IO.File.AppendAllText("D:\OrderDotNet\Log\ExcelHeaders.log", "[" & DateTime.Now.ToString() & "] File: " & filePath & " | Columns: " & headers & Environment.NewLine)
                Catch logEx As Exception
                    LogError("Error logging headers", logEx)
                End Try

                If String.IsNullOrEmpty(suppliercode) Then
                    MessageBox.Show("Supplier code is empty.", "Invalid Supplier", MessageBoxButtons.OK, MessageBoxIcon.Error)
                    txtSupplierSearch.Focus()
                    Exit Sub
                End If

                If String.IsNullOrWhiteSpace(storeName) Then
                    MessageBox.Show("Store name is empty.", "Invalid Store", MessageBoxButtons.OK, MessageBoxIcon.Error)
                    Exit Sub
                End If

                ' Get mappings from SupplierExcelMapping
                Dim mappings As New Dictionary(Of String, String)()
                Try
                    Using conn As New SqlConnection(destinationConnectionString)
                        conn.Open()
                        logBuilder.AppendLine("[INFO] Opened connection for SupplierExcelMapping.")

                        Dim cmd As New SqlCommand("SELECT SupplierColumnName, ColumnName FROM SupplierExcelMapping WHERE SupplierCode = @SupplierCode AND StoreName = @StoreName", conn)
                        cmd.Parameters.AddWithValue("@SupplierCode", suppliercode)
                        cmd.Parameters.AddWithValue("@StoreName", storeName)

                        Using reader As SqlDataReader = cmd.ExecuteReader()
                            While reader.Read()
                                Dim supplierCol As String = reader("SupplierColumnName").ToString()
                                Dim standardCol As String = reader("ColumnName").ToString()
                                If Not mappings.ContainsKey(supplierCol) Then
                                    mappings.Add(supplierCol, standardCol)
                                End If
                            End While
                        End Using
                    End Using
                Catch mapEx As Exception
                    LogError("Error reading SupplierExcelMapping", mapEx)
                    logBuilder.AppendLine("[ERROR] SupplierExcelMapping error: " & mapEx.Message)
                    System.IO.File.AppendAllText(logPath, logBuilder.ToString())
                    Exit Sub
                End Try

                ' Rename columns in DataTable based on mappings
                Dim renamedColumns As New List(Of String)()
                Dim dtColumnsLower As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase)

                ' Build a lowercase -> original mapping for safe renaming
                For Each col As DataColumn In dt.Columns
                    Dim cleanColName As String = col.ColumnName.Trim()
                    dtColumnsLower(cleanColName) = col.ColumnName
                Next

                For Each kvp In mappings
                    Dim excelCol As String = kvp.Key.Trim()
                    Dim sqlCol As String = kvp.Value.Trim()

                    If dtColumnsLower.ContainsKey(excelCol) Then
                        Try
                            Dim originalName As String = dtColumnsLower(excelCol)
                            If Not dt.Columns.Contains(sqlCol) Then
                                dt.Columns(originalName).ColumnName = sqlCol
                                renamedColumns.Add(sqlCol)
                                logBuilder.AppendLine("[INFO] Renamed column: '" & originalName & "' => '" & sqlCol & "'")
                            End If
                        Catch colRenameEx As Exception
                            logBuilder.AppendLine("[ERROR] Failed to rename column: '" & excelCol & "' => '" & sqlCol & "'. " & colRenameEx.Message)
                        End Try
                    Else
                        logBuilder.AppendLine("[WARN] Column not found in Excel: '" & excelCol & "'")
                    End If
                Next


                ' Add required columns if missing
                Dim requiredColsWithTypes As New Dictionary(Of String, Type) From {
                    {"SupplierCode", GetType(String)},
                    {"StoreName", GetType(String)},
                    {"Stock", GetType(Double)},
                    {"TransactionDate", GetType(DateTime)}
                }
                For Each reqCol In requiredColsWithTypes
                    If Not dt.Columns.Contains(reqCol.Key) Then
                        dt.Columns.Add(reqCol.Key, reqCol.Value).DefaultValue = If(reqCol.Key = "SupplierCode", suppliercode,
                                                                                   If(reqCol.Key = "StoreName", storeName,
                                                                                   If(reqCol.Key = "Stock", 100,
                                                                                   CType(DateTime.Now, Object))))
                        logBuilder.AppendLine("[INFO] Added missing column: " & reqCol.Key)
                    End If
                Next

                ' Ensure SupplierCode and StoreName are not null or empty in any row
                For Each row As DataRow In dt.Rows
                    If row.IsNull("SupplierCode") OrElse String.IsNullOrWhiteSpace(row("SupplierCode").ToString()) Then
                        row("SupplierCode") = suppliercode
                    End If
                    If row.IsNull("StoreName") OrElse String.IsNullOrWhiteSpace(row("StoreName").ToString()) Then
                        row("StoreName") = storeName
                    End If
                Next
                dt.AcceptChanges()
                logBuilder.AppendLine("[INFO] Verified all rows have SupplierCode and StoreName populated.")


                ' Remove rows with missing SupplierProductCode
                Dim rowsToRemove As New List(Of DataRow)()
                For Each row As DataRow In dt.Rows
                    If row.IsNull("SupplierProductCode") OrElse String.IsNullOrWhiteSpace(row("SupplierProductCode").ToString()) Then
                        rowsToRemove.Add(row)
                        System.IO.File.AppendAllText("D:\OrderDotNet\Log\ImportExcel_MissingSupplierProductCode.log", "[" & DateTime.Now.ToString() & "] Missing SupplierProductCode in: " & filePath & Environment.NewLine)
                    End If
                Next
                For Each row In rowsToRemove
                    dt.Rows.Remove(row)
                Next
                dt.AcceptChanges()

                Using connection As New SqlConnection(destinationConnectionString)
                    Try
                        connection.Open()
                        logBuilder.AppendLine("[INFO] Opened connection for bulk insert.")

                        If dt.Rows.Count > 0 Then
                            ClearSupplierStockData(suppliercode, connection)
                        End If

                        ' Get destination columns
                        Dim destinationColumns As New HashSet(Of String)(StringComparer.OrdinalIgnoreCase)
                        Try
                            If connection.State <> ConnectionState.Open Then connection.Open()

                            Using cmd As New SqlCommand("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'SupplierStock'", connection)
                                Using reader As SqlDataReader = cmd.ExecuteReader()
                                    While reader.Read()
                                        destinationColumns.Add(reader("COLUMN_NAME").ToString().Trim())
                                    End While
                                End Using
                            End Using
                        Catch colEx As Exception
                            logBuilder.AppendLine("[ERROR] Failed to retrieve column names: " & colEx.Message)
                            logBuilder.AppendLine("Stack Trace: " & colEx.StackTrace)
                            System.IO.File.AppendAllText(logPath, logBuilder.ToString())
                            LogError("Error retrieving destination columns", colEx)
                            Exit Sub
                        End Try


                        ' Drop extra columns not found in destination
                        Dim colsToRemove As New List(Of DataColumn)()
                        For Each col As DataColumn In dt.Columns
                            Dim cleanColName As String = col.ColumnName.Trim()
                            If Not destinationColumns.Contains(cleanColName) Then
                                colsToRemove.Add(col)
                                logBuilder.AppendLine("[INFO] Dropping unmapped column: '" & col.ColumnName & "' (cleaned: '" & cleanColName & "')")
                            End If
                        Next
                        For Each col In colsToRemove
                            dt.Columns.Remove(col)
                        Next
                        dt.AcceptChanges()


                        For Each col As DataColumn In dt.Columns
                            col.ColumnName = col.ColumnName.ToLower()
                        Next
                        logBuilder.AppendLine("Final DataTable columns before bulk copy: " & _
                            String.Join(", ", dt.Columns.Cast(Of DataColumn).Select(Function(c) "'" & c.ColumnName.Trim() & "'")))

                        ' Perform bulk insert
                        Using bulkCopy As New SqlBulkCopy(connection)
                            bulkCopy.DestinationTableName = "SupplierStock"

                            ' Map columns that exist in both dt and destination table and build a detailed log
                            logBuilder.AppendLine("SqL_Column_name" & vbTab & "DT_columns")
                            For Each col As DataColumn In dt.Columns
                                Dim sourceCol As String = col.ColumnName
                                Dim destCol As String = col.ColumnName ' Assuming lowercase match
                                If destinationColumns.Contains(destCol) Then
                                    bulkCopy.ColumnMappings.Add(sourceCol, destCol)
                                    logBuilder.AppendLine(destCol & vbTab & sourceCol)
                                End If
                            Next

                            For Each col As DataColumn In dt.Columns
                                Select Case col.ColumnName.ToLower()
                                    Case "suppliercode" : col.ColumnName = "SupplierCode"
                                    Case "supplierproductcode" : col.ColumnName = "SupplierProductCode"
                                    Case "supplierproductname" : col.ColumnName = "SupplierProductName"
                                    Case "packing" : col.ColumnName = "Packing"
                                    Case "storename" : col.ColumnName = "StoreName"
                                    Case "stock" : col.ColumnName = "Stock"
                                    Case "transactiondate" : col.ColumnName = "TransactionDate"
                                    Case "minqty" : col.ColumnName = "minqty"
                                End Select
                            Next

                            Try
                                bulkCopy.WriteToServer(dt)
                                MessageBox.Show("Bulk insert completed successfully.")
                                logBuilder.AppendLine("[INFO] Bulk insert completed.")
                            Catch exBulk As Exception
                                logBuilder.AppendLine("[ERROR] SQL bulk insert: " & exBulk.Message)
                                logBuilder.AppendLine("Stack Trace: " & exBulk.StackTrace)
                                System.IO.File.AppendAllText(logPath, logBuilder.ToString())
                                LogError("Error during SQL bulk insert", exBulk)
                                MessageBox.Show("Error during bulk insert: " & exBulk.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                            End Try
                        End Using

                    Catch connEx As Exception
                        logBuilder.AppendLine("[ERROR] Connection or SQL execution error during bulk insert phase: " & connEx.Message)
                        logBuilder.AppendLine("Stack Trace: " & connEx.StackTrace)
                        System.IO.File.AppendAllText(logPath, logBuilder.ToString())
                        LogError("Connection or execution error", connEx)
                    End Try
                End Using

            Catch exMain As Exception
                logBuilder.AppendLine("[ERROR] General error during import: " & exMain.Message)
                logBuilder.AppendLine("Stack Trace: " & exMain.StackTrace)
                System.IO.File.AppendAllText(logPath, logBuilder.ToString())
                LogError("General error during import", exMain)
                MessageBox.Show("Error during import: " & exMain.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            End Try
        End If
    End Sub

    Private Function GetSupplierStockTableColumns() As List(Of String)
        Dim columns As New List(Of String)()
        Using conn As New SqlConnection(destinationConnectionString)
            Dim query As String = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'SupplierStock'"
            Using cmd As New SqlCommand(query, conn)
                conn.Open()
                Using reader As SqlDataReader = cmd.ExecuteReader()
                    While reader.Read()
                        columns.Add(reader("COLUMN_NAME").ToString())
                    End While
                End Using
            End Using
        End Using
        Return columns
    End Function


    Private Sub LoadExcelHeadersToDGVMain(dt As DataTable)
        dgvMain.Columns.Clear()
        dgvMain.Rows.Clear()

        dgvMain.Columns.Add("HeaderName", "Excel Column Header")

        For Each col As DataColumn In dt.Columns
            dgvMain.Rows.Add(col.ColumnName)
        Next
        dgvMain.Refresh()
        dgvMain.Visible = True
    End Sub

    Private Sub LoadMappingGrid(dtExcel As DataTable)
        DGVMapping.Columns.Clear()
        DGVMapping.Rows.Clear()

        ' Add HeaderName (SQL column)
        Dim headerCol As New DataGridViewTextBoxColumn()
        headerCol.Name = "HeaderName"
        headerCol.HeaderText = "SupplierStock Column"
        headerCol.ReadOnly = True
        DGVMapping.Columns.Add(headerCol)

        ' Add ExcelColumnHeader (ComboBox)
        Dim cmbCol As New DataGridViewComboBoxColumn()
        cmbCol.Name = "ExcelColumnHeader"
        cmbCol.HeaderText = "Map to Excel Column"
        cmbCol.FlatStyle = FlatStyle.Flat

        ' Load Excel column names into ComboBox
        For Each col As DataColumn In dtExcel.Columns
            cmbCol.Items.Add(col.ColumnName)
        Next

        ' Set editable only for "Supplier Excel Mapping"
        If cboProcess.SelectedItem IsNot Nothing AndAlso cboProcess.SelectedItem.ToString() = "Supplier Excel Mapping" Then
            cmbCol.ReadOnly = False
        End If

        DGVMapping.Columns.Add(cmbCol)

        ' === Load previous mappings from SupplierExcelMapping table ===
        Dim previousMappings As Dictionary(Of String, String) = GetPreviousExcelMappings()

        ' Load SQL SupplierStock columns into HeaderName column
        Dim supplierStockColumns = GetSupplierStockTableColumns()
        For Each sqlCol As String In supplierStockColumns
            Dim rowIndex As Integer = DGVMapping.Rows.Add()
            DGVMapping.Rows(rowIndex).Cells("HeaderName").Value = sqlCol

            ' Set previous Excel column mapping if available
            If previousMappings.ContainsKey(sqlCol) Then
                DGVMapping.Rows(rowIndex).Cells("ExcelColumnHeader").Value = previousMappings(sqlCol)
            End If
        Next

        ConfigureDataGridViewnew(DGVMapping)
        DGVMapping.Visible = True
        DGVMapping.Refresh()
    End Sub

    Private Function GetPreviousExcelMappings() As Dictionary(Of String, String)
        Dim mappings As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase)

        Dim query As String = "SELECT ColumnName AS HeaderName, SupplierColumnName AS ExcelColumnHeader " & _
                              "FROM SupplierExcelMapping " & _
                              "WHERE SupplierCode = @SupplierCode AND StoreName = @StoreName"

        Using conn As New SqlConnection(destinationConnectionString)
            conn.Open()
            Using cmd As New SqlCommand(query, conn)
                ' Use global variables for parameters
                cmd.Parameters.AddWithValue("@SupplierCode", suppliercode)
                cmd.Parameters.AddWithValue("@StoreName", storeName)

                Using reader As SqlDataReader = cmd.ExecuteReader()
                    While reader.Read()
                        Dim sqlCol As String = reader("HeaderName").ToString().Trim()
                        Dim excelCol As String = reader("ExcelColumnHeader").ToString().Trim()
                        If Not mappings.ContainsKey(sqlCol) AndAlso Not String.IsNullOrEmpty(excelCol) Then
                            mappings.Add(sqlCol, excelCol)
                        End If
                    End While
                End Using
            End Using
        End Using

        Return mappings
    End Function



    Public Class SupplierExcelMapping
        Public Property SupplierCode As String
        Public Property SupplierColumnName As String
        Public Property ColumnName As String
        Public Property StoreName As String
    End Class

    Public Sub SaveMappingGridToDatabase()
        Dim mappings As New List(Of SupplierExcelMapping)

        If String.IsNullOrEmpty(suppliercode) OrElse String.IsNullOrEmpty(storeName) Then
            MessageBox.Show("SupplierCode or StoreName is missing.", "Validation Error", MessageBoxButtons.OK, MessageBoxIcon.Warning)
            Return
        End If

        For Each row As DataGridViewRow In DGVMapping.Rows
            If Not row.IsNewRow Then
                Dim sqlCol As String = Convert.ToString(row.Cells("HeaderName").Value)
                Dim excelCol As String = Convert.ToString(row.Cells("ExcelColumnHeader").Value)

                If Not String.IsNullOrWhiteSpace(sqlCol) AndAlso Not String.IsNullOrWhiteSpace(excelCol) Then
                    mappings.Add(New SupplierExcelMapping With {
                        .SupplierCode = suppliercode,
                        .ColumnName = sqlCol,
                        .SupplierColumnName = excelCol,
                        .StoreName = storeName
                    })
                End If
            End If
        Next

        If mappings.Count > 0 Then
            SaveSupplierExcelMappingToDB(mappings)
            MessageBox.Show("Mappings saved successfully.", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information)
        Else
            MessageBox.Show("No valid mappings to save.", "Warning", MessageBoxButtons.OK, MessageBoxIcon.Warning)
        End If
    End Sub

    Public Sub SaveSupplierExcelMappingToDB(mappings As List(Of SupplierExcelMapping))
        Using conn As New SqlConnection(destinationConnectionString)
            conn.Open()

            ' Create table if not exists
            Dim createTableSql As String = _
                "IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SupplierExcelMapping') " & _
                "BEGIN " & _
                "CREATE TABLE SupplierExcelMapping (" & _
                "SupplierCode NVARCHAR(50), " & _
                "SupplierColumnName NVARCHAR(100), " & _
                "ColumnName NVARCHAR(100), " & _
                "StoreName NVARCHAR(100), " & _
                "PRIMARY KEY (SupplierCode, StoreName, ColumnName)" & _
                ")" & _
                " END"

            Using createCmd As New SqlCommand(createTableSql, conn)
                createCmd.ExecuteNonQuery()
            End Using

            ' Insert or update rows
            For Each mapping In mappings
                Dim checkQuery As String = _
                    "SELECT COUNT(1) FROM SupplierExcelMapping " & _
                    "WHERE SupplierCode = @SupplierCode AND StoreName = @StoreName AND ColumnName = @ColumnName"

                Using checkCmd As New SqlCommand(checkQuery, conn)
                    checkCmd.Parameters.AddWithValue("@SupplierCode", mapping.SupplierCode)
                    checkCmd.Parameters.AddWithValue("@StoreName", mapping.StoreName)
                    checkCmd.Parameters.AddWithValue("@ColumnName", mapping.ColumnName)

                    Dim exists As Integer = Convert.ToInt32(checkCmd.ExecuteScalar())

                    If exists > 0 Then
                        ' Update
                        Dim updateQuery As String = _
                            "UPDATE SupplierExcelMapping SET " & _
                            "SupplierColumnName = @SupplierColumnName " & _
                            "WHERE SupplierCode = @SupplierCode AND StoreName = @StoreName AND ColumnName = @ColumnName"

                        Using updateCmd As New SqlCommand(updateQuery, conn)
                            updateCmd.Parameters.AddWithValue("@SupplierColumnName", mapping.SupplierColumnName)
                            updateCmd.Parameters.AddWithValue("@SupplierCode", mapping.SupplierCode)
                            updateCmd.Parameters.AddWithValue("@StoreName", mapping.StoreName)
                            updateCmd.Parameters.AddWithValue("@ColumnName", mapping.ColumnName)
                            updateCmd.ExecuteNonQuery()
                        End Using
                    Else
                        ' Insert
                        Dim insertQuery As String = _
                            "INSERT INTO SupplierExcelMapping (SupplierCode, SupplierColumnName, ColumnName, StoreName) " & _
                            "VALUES (@SupplierCode, @SupplierColumnName, @ColumnName, @StoreName)"

                        Using insertCmd As New SqlCommand(insertQuery, conn)
                            insertCmd.Parameters.AddWithValue("@SupplierCode", mapping.SupplierCode)
                            insertCmd.Parameters.AddWithValue("@SupplierColumnName", mapping.SupplierColumnName)
                            insertCmd.Parameters.AddWithValue("@ColumnName", mapping.ColumnName)
                            insertCmd.Parameters.AddWithValue("@StoreName", mapping.StoreName)
                            insertCmd.ExecuteNonQuery()
                        End Using
                    End If
                End Using
            Next
        End Using
    End Sub

    Private Sub LogError(message As String, ex As Exception)
        Dim logPath As String = "D:\OrderDotNet\Log\ImportExcel.log"
        Dim logEntry As String = "[" & DateTime.Now.ToString() & "] " & message & ": " & ex.Message & Environment.NewLine &
                                 "Stack Trace: " & ex.StackTrace & Environment.NewLine & Environment.NewLine

        Try
            System.IO.File.AppendAllText(logPath, logEntry)
        Catch
            ' Fails silently if log file can't be written
        End Try
    End Sub


    Private Function ReadExcelFileUsingInterop(filePath As String) As DataTable
        Dim dt As New DataTable()

        ' Excel COM objects
        Dim excelApp As New Excel.Application
        Dim workbooks As Excel.Workbooks = excelApp.Workbooks
        Dim workbook As Excel.Workbook = Nothing
        Dim worksheet As Excel.Worksheet = Nothing
        Dim range As Excel.Range = Nothing

        Try
            workbook = workbooks.Open(filePath)
            worksheet = CType(workbook.Sheets(1), Excel.Worksheet)
            range = worksheet.UsedRange

            If range Is Nothing OrElse range.Rows.Count = 0 OrElse range.Columns.Count = 0 Then
                MessageBox.Show("The Excel sheet is empty or invalid.", "Data Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                Return Nothing
            End If

            Dim rowCount As Integer = range.Rows.Count
            Dim colCount As Integer = range.Columns.Count
            Dim values As Object(,) = CType(range.Value2, Object(,))

            ' === STEP 1: Build column headers from first row ===
            For col As Integer = 1 To colCount
                Dim header As String = If(values(1, col) IsNot Nothing, values(1, col).ToString().Trim(), "Column" & col.ToString())
                If Not dt.Columns.Contains(header) Then
                    dt.Columns.Add(header)
                Else
                    dt.Columns.Add(header & "_1")
                End If
            Next

            ' === STEP 2: Build all data rows at once (no row-by-row looping) ===
            Dim tempTable As Object(,) = New Object(rowCount - 2, colCount - 1) {} ' Since we skip header

            For i As Integer = 2 To rowCount
                For j As Integer = 1 To colCount
                    Dim value As Object = values(i, j)
                    tempTable(i - 2, j - 1) = If(value IsNot Nothing, value.ToString(), DBNull.Value)
                Next
            Next

            ' === STEP 3: Load the array into DataTable ===
            For i As Integer = 0 To tempTable.GetLength(0) - 1
                Dim row As DataRow = dt.NewRow()
                For j As Integer = 0 To tempTable.GetLength(1) - 1
                    row(j) = tempTable(i, j)
                Next
                dt.Rows.Add(row)
            Next

        Catch ex As Exception
            MessageBox.Show("Error while reading Excel file: " & ex.Message, "File Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return Nothing
        Finally
            If workbook IsNot Nothing Then workbook.Close(False)
            excelApp.Quit()

            ' Release COM objects
            ReleaseComObject(range)
            ReleaseComObject(worksheet)
            ReleaseComObject(workbook)
            ReleaseComObject(workbooks)
            ReleaseComObject(excelApp)
        End Try

        Return dt
    End Function


    ' Helper method to release COM objects
    Private Sub ReleaseComObject(ByVal obj As Object)
        Try
            If obj IsNot Nothing Then
                System.Runtime.InteropServices.Marshal.ReleaseComObject(obj)
                obj = Nothing
            End If
        Catch ex As Exception
            obj = Nothing
        End Try
    End Sub

    Private Sub ClearSupplierStockData(SupplierCode As String, connection As SqlConnection)
        Try
            ' Open the connection if it's closed
            If connection.State = ConnectionState.Closed Then
                connection.Open()
            End If

            ' Prepare the delete command with SupplierCode and StoreName filters
            Dim deleteQuery As String = "DELETE FROM supplierstock WHERE suppliercode = @Suppliercode AND storename = @StoreName"
            Dim deleteCommand As New SqlCommand(deleteQuery, connection)

            ' Add parameters
            deleteCommand.Parameters.AddWithValue("@Suppliercode", SupplierCode)
            deleteCommand.Parameters.AddWithValue("@StoreName", storename) ' ← Use your global variable here

            ' Execute deletion
            deleteCommand.ExecuteNonQuery()

            MessageBox.Show("Existing data cleared successfully.")
        Catch ex As Exception
            MessageBox.Show("Error clearing existing data: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        Finally
            ' Always close the connection after use
            If connection.State = ConnectionState.Open Then
                connection.Close()
            End If
        End Try
    End Sub


    ' Function to select folder using FolderBrowserDialog
    Private Function SelectFolder() As String
        Dim folderDialog As New FolderBrowserDialog()
        If folderDialog.ShowDialog() = DialogResult.OK Then
            Return folderDialog.SelectedPath
        Else
            Return String.Empty
        End If
    End Function

    Public Sub ProcessExcelFilesAndExportInvnoWise()
        ' Step 1: Select folder to process Excel files
        Dim folderPath As String = SelectFolder()
        If String.IsNullOrEmpty(folderPath) Then
            MessageBox.Show("No folder selected.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return
        End If

        ' Step 2: Create a folder for today's date
        Dim todayFolder As String = Path.Combine(folderPath, DateTime.Now.ToString("yyyy-MM-dd"))
        If Not Directory.Exists(todayFolder) Then
            Directory.CreateDirectory(todayFolder)
        End If

        ' Step 3: Get all Excel files from the selected folder and load into a DataTable
        Dim excelFiles As String() = Directory.GetFiles(folderPath, "*.xls*")
        If excelFiles.Length = 0 Then
            MessageBox.Show("No Excel files found.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return
        End If

        Dim allData As New DataTable()
        For Each filePath As String In excelFiles
            Try
                Dim dataTable As DataTable = ReadFirstSheetFromExcelFile(filePath)
                If dataTable IsNot Nothing AndAlso dataTable.Rows.Count > 0 Then
                    allData.Merge(dataTable) ' Combine data from all Excel files
                End If
            Catch ex As Exception
                MessageBox.Show("Error reading Excel file: " & filePath, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                Continue For
            End Try
        Next

        If allData.Rows.Count = 0 Then
            MessageBox.Show("No data found in any Excel file.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return
        End If

        ' Step 4: Fetch rack details in bulk for all unique codes in the data
        Dim uniqueCodes As List(Of String) = allData.AsEnumerable().
                                              Select(Function(row) row.Field(Of String)("code")).Distinct().ToList()

        ' Fetch rack details for all codes from the database
        Dim rackValues As Dictionary(Of String, String) = GetRackValuesForCodes(uniqueCodes)

        ' Step 5: Update 'Rack' column in the DataTable
        If Not allData.Columns.Contains("Rack") Then
            allData.Columns.Add("Rack", GetType(String))
        End If

        For Each row As DataRow In allData.Rows
            Dim code As String = row("code").ToString().Trim()
            If rackValues.ContainsKey(code) Then
                row("Rack") = rackValues(code)
            End If
        Next

        ' Step 6: Split DataTable by 'invno' and export to separate Excel files
        Dim groupedData = allData.AsEnumerable().GroupBy(Function(row) row.Field(Of String)("invno"))

        For Each group In groupedData
            Dim invNo As String = group.Key
            Dim invData As DataTable = group.CopyToDataTable()

            ' Save the DataTable as a new Excel file
            Dim newFilePath As String = Path.Combine(todayFolder, invNo & " Processed.xls")
            Me.Text = "Order Ver 1.4.2      " & newFilePath
            SaveToExcel(invData, newFilePath)
        Next

        MessageBox.Show("Process completed.", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information)
        Me.Text = "Order Ver 1.4.2"
    End Sub

    Private Sub SaveToExcel(dataTable As DataTable, filePath As String)
        ' Sort the data by "Rack" in ascending order and "name" in descending order
        Dim dataView As New DataView(dataTable)
        dataView.Sort = "Rack ASC,name ASC" ' Sorting by "item_name" DESC and "rack" ASC

        ' Create Excel application object
        Dim excelApp As New Excel.Application
        Dim workbook As Excel.Workbook = excelApp.Workbooks.Add()
        Dim worksheet As Excel.Worksheet = CType(workbook.Sheets(1), Excel.Worksheet)

        ' Write headers and add 'tax', 'tcs', 'disamt' and 'invamt' column headers
        For colIndex As Integer = 0 To dataTable.Columns.Count - 1
            worksheet.Cells(1, colIndex + 1).Value = dataTable.Columns(colIndex).ColumnName
        Next
        worksheet.Cells(1, dataTable.Columns.Count + 1).Value = "tax" ' Add the 'tax' column header
        worksheet.Cells(1, dataTable.Columns.Count + 2).Value = "tcs" ' Add the 'tcs' column header
        worksheet.Cells(1, dataTable.Columns.Count + 3).Value = "disamt" ' Add the 'disamt' column header
        worksheet.Cells(1, dataTable.Columns.Count + 4).Value = "Invamt" ' Add the 'Invamt' column header

        ' Variables for summing totals
        Dim totalAmount As Double = 0
        Dim totalDisAmt As Double = 0
        Dim totalTax As Double = 0
        Dim totalTCS As Double = 0
        Dim finalInvAmt As Double = 0

        ' Write data from the sorted DataView and add 'tax', 'tcs', 'disamt' and 'invamt' columns
        For rowIndex As Integer = 0 To dataView.Count - 1
            For colIndex As Integer = 0 To dataTable.Columns.Count - 1
                Dim cellValue As String = dataView(rowIndex)(colIndex).ToString()

                ' Log and handle 'code' values with leading zeros
                If dataTable.Columns(colIndex).ColumnName.ToLower() = "code" Then
                    ' Ensure that the value is written as text to retain leading zeros
                    worksheet.Cells(rowIndex + 2, colIndex + 1).NumberFormat = "@"
                    worksheet.Cells(rowIndex + 2, colIndex + 1).Value = cellValue
                ElseIf dataTable.Columns(colIndex).ColumnName.ToLower() = "exp" Then
                    ' Handle 'exp' (expiry date) column
                    If Not String.IsNullOrEmpty(cellValue) Then
                        ' Force the value to be treated as text
                        worksheet.Cells(rowIndex + 2, colIndex + 1).NumberFormat = "@"
                        ' Ensure the date is written in DD-MM-YYYY format
                        Dim expDate As DateTime
                        ' Try parsing the date using the format dd-MM-yyyy
                        If DateTime.TryParseExact(cellValue, "dd-MM-yyyy", Nothing, Globalization.DateTimeStyles.None, expDate) Then
                            worksheet.Cells(rowIndex + 2, colIndex + 1).Value = expDate.ToString("dd-MM-yyyy")
                        Else
                            ' If parsing fails, keep it empty or handle the invalid date case
                            worksheet.Cells(rowIndex + 2, colIndex + 1).Value = ""
                        End If
                    End If
                Else
                    worksheet.Cells(rowIndex + 2, colIndex + 1).Value = cellValue
                End If
            Next

            ' Retrieve values for calculations
            Dim sRate As Double = 0
            Dim dis As Double = 0
            Dim gst As Double = 0
            Dim qty As Double = 0 ' Initialize qty variable
            Dim amount As Double = 0

            ' Check if the necessary columns are present in the data
            If dataTable.Columns.Contains("s_rate") AndAlso dataTable.Columns.Contains("dis") AndAlso dataTable.Columns.Contains("gst") AndAlso dataTable.Columns.Contains("qty") AndAlso dataTable.Columns.Contains("Amount") Then
                ' Retrieve values from the current row and calculate tax
                If Not dataView(rowIndex).Item("s_rate") Is DBNull.Value Then
                    sRate = Convert.ToDouble(dataView(rowIndex).Item("s_rate"))
                End If
                If Not dataView(rowIndex).Item("dis") Is DBNull.Value Then
                    dis = Convert.ToDouble(dataView(rowIndex).Item("dis"))
                End If
                If Not dataView(rowIndex).Item("gst") Is DBNull.Value Then
                    gst = Convert.ToDouble(dataView(rowIndex).Item("gst"))
                End If
                If Not dataView(rowIndex).Item("qty") Is DBNull.Value Then
                    qty = Convert.ToDouble(dataView(rowIndex).Item("qty"))
                End If
                If Not dataView(rowIndex).Item("Amount") Is DBNull.Value Then
                    amount = Convert.ToDouble(dataView(rowIndex).Item("Amount"))
                End If

                ' Calculate discounted rate: s_rate - (s_rate * dis / 100)
                Dim discountedRate As Double = sRate - (sRate * dis / 100)

                ' Calculate tax: discounted_rate * gst / 100 * qty
                Dim tax As Double = discountedRate * gst / 100 * qty

                ' Calculate TCS (Tax Collected at Source): amount * 1%
                Dim tcs As Double = amount * 0.001

                ' Calculate DisAmt (Discount Amount): s_rate * (dis / 100) * qty
                Dim disAmt As Double = sRate * (dis / 100) * qty

                ' Calculate InvAmt (Invoice Amount): (Amount - DisAmt) + Tax + TCS
                Dim invAmt As Double = (amount - disAmt) + tax + tcs

                ' Round invAmt to 2 decimal places
                invAmt = Math.Round(invAmt, 2)

                ' Store the calculated values in the Excel columns
                worksheet.Cells(rowIndex + 2, dataTable.Columns.Count + 1).Value = tax
                worksheet.Cells(rowIndex + 2, dataTable.Columns.Count + 2).Value = tcs
                worksheet.Cells(rowIndex + 2, dataTable.Columns.Count + 3).Value = disAmt
                worksheet.Cells(rowIndex + 2, dataTable.Columns.Count + 4).Value = invAmt ' Add finalInvAmt to "Invamt" column

                ' Sum up the values for final calculation
                totalAmount += amount
                totalDisAmt += disAmt
                totalTax += tax
                totalTCS += tcs
            End If
        Next

        ' Calculate the final Invamt as sum of all rows: (sum(amount) - sum(disamt)) + sum(tax) + sum(tcs)
        finalInvAmt = (totalAmount - totalDisAmt) + totalTax + totalTCS

        ' Round finalInvAmt to 2 decimal places
        finalInvAmt = Math.Round(finalInvAmt, 0)

        ' Now assign the same Invamt value to all rows
        For rowIndex As Integer = 0 To dataView.Count - 1
            worksheet.Cells(rowIndex + 2, dataTable.Columns.Count + 4).Value = finalInvAmt
        Next

        ' Save the workbook in Excel 97-2003 format (.xls)
        workbook.SaveAs(filePath, Excel.XlFileFormat.xlExcel8)  ' Excel 97-2003 format

        ' Close the workbook and Excel application
        workbook.Close(False)
        excelApp.Quit()

        ' Release COM objects
        Marshal.ReleaseComObject(worksheet)
        Marshal.ReleaseComObject(workbook)
        Marshal.ReleaseComObject(excelApp)
    End Sub

    Private Function ReadFirstSheetFromExcelFile(filePath As String) As DataTable
        Dim dataTable As New DataTable()
        Try
            ' Create Excel application object
            Dim excelApp As New Excel.Application
            Dim workbook As Excel.Workbook = excelApp.Workbooks.Open(filePath)
            Dim worksheet As Excel.Worksheet = CType(workbook.Sheets(1), Excel.Worksheet)

            ' Read entire sheet content into DataTable
            Dim range As Excel.Range = worksheet.UsedRange
            Dim rows As Integer = range.Rows.Count
            Dim columns As Integer = range.Columns.Count

            ' Add headers to DataTable
            For colIndex As Integer = 1 To columns
                Dim columnName As String = range.Cells(1, colIndex).Value.ToString().Trim()
                dataTable.Columns.Add(columnName)

                ' Set 'code' column to String (Text) explicitly
                If columnName.ToLower() = "code" Then
                    dataTable.Columns(columnName).DataType = GetType(String) ' Ensure 'code' column is treated as string
                End If
            Next

            ' Bulk read data into a 2D array
            Dim cellValues As Object(,) = range.Value

            ' Add data rows to DataTable
            For rowIndex As Integer = 2 To rows
                Dim dataRow As DataRow = dataTable.NewRow()
                For colIndex As Integer = 1 To columns
                    Dim columnName As String = dataTable.Columns(colIndex - 1).ColumnName

                    If columnName.ToLower() = "code" Then
                        ' Ensure 'code' is treated as string and handle any potential issues with formatting
                        Dim codeValue As String = String.Empty
                        Dim cellValue As Object = cellValues(rowIndex, colIndex)

                        If cellValue IsNot Nothing Then
                            codeValue = cellValue.ToString().Trim()

                            ' Log the details of the code with leading zero
                            If codeValue.StartsWith("0") Then
                                LogCodeWithLeadingZero(rowIndex, colIndex, codeValue)
                            End If
                        End If

                        ' Ensure code is treated as a string with leading zeros preserved
                        If String.IsNullOrEmpty(codeValue) Then
                            codeValue = "Unknown"
                        End If
                        dataRow(colIndex - 1) = codeValue
                    Else
                        Dim cellValue As Object = cellValues(rowIndex, colIndex)
                        If cellValue IsNot Nothing Then
                            dataRow(colIndex - 1) = cellValue.ToString().Trim()
                        Else
                            dataRow(colIndex - 1) = String.Empty
                        End If
                    End If
                Next
                dataTable.Rows.Add(dataRow)
            Next

            ' Close workbook and quit Excel
            workbook.Close(False)
            excelApp.Quit()

            ' Release COM objects
            Marshal.ReleaseComObject(worksheet)
            Marshal.ReleaseComObject(workbook)
            Marshal.ReleaseComObject(excelApp)

        Catch ex As Exception
            MessageBox.Show("Error reading Excel file " & filePath & ": " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return Nothing
        End Try

        Return dataTable
    End Function



    Private Sub LogCodeWithLeadingZero(rowIndex As Integer, colIndex As Integer, codeValue As String)
        ' Log the code that starts with '0' for debugging purposes
        Dim logMessage As String = "Code with leading zero detected at Row " & rowIndex & ", Column " & colIndex & ": " & codeValue

        ' Log to file path: d:\OrderDotNet\Log\ExcelReading.log
        Dim logFilePath As String = "d:\OrderDotNet\Log\ExcelReading.log"
        Try
            ' Ensure the directory exists
            Dim directory As String = Path.GetDirectoryName(logFilePath)

            ' Write the log message to the file
            File.AppendAllText(logFilePath, logMessage & Environment.NewLine)
        Catch ex As Exception
            ' If file writing fails, show a message box
            MessageBox.Show("Error logging the code: " & ex.Message, "Log Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub


    Private Sub LoadDataForSupplier(supplierCode As String)
        Const sql As String =
                             "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.TotalStock, om.SlsQty, " &
                             "       om.UnitDescription, om.SaleUnit, om.MRP, " &
                             "       om.MaxSaleQty, om.TransactionDate, om.remarks, om.WantedType, " &
                             "       om.LastReceivedDate, om.LastSaleDate, op.StoreName, om.ProductTypeName, " &
                             "       om.QtyCheck " &
                             "FROM OrderManagement om " &
                             "INNER JOIN OrderPurchaseTrans op ON op.ProductCode = om.ProductCode AND op.StoreName = om.StoreName " &
                             "WHERE om.Status = 0 " &
                             "  AND om.OrderQty > 0 " &
                             "  AND om.ProductTypeName IN ('Pharma', 'Non Pharma') " &
                             "  AND op.SupplierCode IN (SELECT Value FROM dbo.SplitString(@suppliercode, ',')) " &
                             "  AND om.StoreName = @storename " &
                             "ORDER BY om.ProductTypeName, om.ProductName"


        Dim parameters As New Dictionary(Of String, Object) From {
            {"@suppliercode", supplierCode},
            {"@storename", storeName}
        }

        LoadDataGridView2(sql, parameters)
    End Sub

    Private Sub CompareOrderManagement(orderId As Double)
        Dim query As String =
            "UPDATE om SET " &
            "    om.orqty = omb.orqty, " &
            "    om.orsupplier = omb.orsupplier, " &
            "    om.status = 2, " &
            "    om.remarks = @remarks " &
            "FROM OrderManagement om " &
            "INNER JOIN OrderManagementBackup omb ON om.productcode = omb.productcode " &
            "WHERE omb.orderid = @orderid " &
            "  AND (omb.status = 1 OR omb.status = 0) " &
            "  AND om.storename = @storename " &
            "  AND ( " &
            "       (omb.totalstock > om.totalstock AND om.storename = omb.storename) " &
            "       OR (omb.status = 1 OR omb.orderqty = 0) " &
            "  ); " & vbCrLf &
            "UPDATE om SET " &
            "    om.orderqty = (om.Orgorderqty - omb.orqty), " &
            "    om.status = 0, " &
            "    om.remarks = 'After Order Sold', " &
            "    om.wantedtype = 'After Order Sold' " &
            "FROM OrderManagement om " &
            "INNER JOIN OrderManagementBackup omb ON om.productcode = omb.productcode " &
            "WHERE omb.orderid = @orderid " &
            "  AND om.storename = @storename " &
            "  AND omb.totalstock > om.totalstock " &
            "  AND om.storename = omb.storename " &
            "  AND (om.orderqty - omb.orqty) > 0;"

        Try
            Using conn As New SqlConnection(destinationConnectionString)
                Using cmd As New SqlCommand(query, conn)
                    cmd.Parameters.AddWithValue("@orderid", orderId)
                    cmd.Parameters.AddWithValue("@remarks", "Compare Order with " & orderId)
                    cmd.Parameters.AddWithValue("@storename", storeName)

                    conn.Open()
                    cmd.ExecuteNonQuery()
                End Using
            End Using

            MessageBox.Show("Order comparison completed successfully.", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information)

        Catch ex As Exception
            MessageBox.Show("Error comparing order: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
        cboProcess.Focus()
    End Sub


    Private Sub FetchSupplierOrderDetails()
        Dim connectionString As String = destinationConnectionString
        Dim query As String =
            "SELECT productcode, productname,OrderQty, saleunit, mrp, orsupplier, remarks " &
            "FROM ordermanagement " &
            "WHERE status = 1 " &
            "AND orsuppliercode IN (SELECT Value FROM dbo.SplitString(@suppliercode, ',')) " &
            "AND storename = @storename " &
            "AND orderqty > 0 " &
            "ORDER BY productname"

        Using connection As New SqlConnection(connectionString)
            Using command As New SqlCommand(query, connection)
                command.Parameters.AddWithValue("@suppliercode", suppliercode) ' Use global variable
                command.Parameters.AddWithValue("@storename", storeName)

                Try
                    connection.Open()
                    Dim adapter As New SqlDataAdapter(command)
                    Dim dataTable As New DataTable()
                    adapter.Fill(dataTable)

                    If dataTable.Rows.Count = 0 Then
                        MessageBox.Show("No Order Placed for this Supplier", "Info", MessageBoxButtons.OK, MessageBoxIcon.Information)
                        Exit Sub
                    End If

                    ' Add SerialNo column and fill values
                    dataTable.Columns.Add("SerialNo", GetType(Integer))
                    For i As Integer = 0 To dataTable.Rows.Count - 1
                        dataTable.Rows(i)("SerialNo") = i + 1
                    Next
                    dataTable.Columns("SerialNo").SetOrdinal(0)

                    ' Bind to DataGridView
                    dgvMain.DataSource = dataTable
                    dgvMain.Visible = True

                    ' Apply standard configuration
                    ConfigureDataGridViewnew(dgvMain)
                    dgvMain.Focus()

                Catch ex As Exception
                    MessageBox.Show("Error loading supplier order details: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                End Try
            End Using
        End Using
    End Sub

    Private Sub HandlePendingOrder()
        Try
            ' === Validate product type selection ===
            If cboProductType.SelectedItem Is Nothing Then
                MessageBox.Show("Please select a valid item from the product type list.")
                Return
            End If

            ' === Handle supplier selection from dgvSupplierList ===
            If dgvSupplierList.CurrentRow IsNot Nothing AndAlso dgvSupplierList.Visible Then
                Dim supplierCodeLocal As String = dgvSupplierList.CurrentRow.Cells(0).Value.ToString()
                Dim supplierName As String = dgvSupplierList.CurrentRow.Cells(1).Value.ToString()

                txtSupplierSearch.Text = supplierName
                suppliercode = supplierCodeLocal

                dgvSupplierList.DataSource = Nothing
                dgvSupplierList.Refresh()
                dgvSupplierList.Visible = False

                LoadDataForSupplier(supplierCodeLocal)
            Else
                txtSupplierSearch.Text = "Pending Order"
                suppliercode = "Pending"
                CboSelect.Visible = False
                dgvSupplierList.DataSource = Nothing
                dgvSupplierList.Refresh()
                dgvSupplierList.Visible = False
            End If

            ' === Construct SQL query ===
            Dim selectedValue As String = cboProductType.SelectedItem.ToString()
            Dim query As String = If(selectedValue = "All",
                <sql>
            SELECT productcode, productname, orderqty, totalstock, slsqty, unitdescription, 
                   saleunit, mrp, lastreceiveddate, lastsaledate, maxsaleqty, 
                   Transactiondate, wantedtype
            FROM ordermanagement
            WHERE qtycheck = 1 
                  AND producttypename IN ('Pharma', 'Non Pharma')
                  AND storename = @storename
                  AND status = 0
                  AND orderqty > 0
            ORDER BY productname
        </sql>.Value,
                <sql>
            SELECT productcode, productname, orderqty, totalstock, slsqty, unitdescription, 
                   saleunit, mrp, lastreceiveddate, lastsaledate, maxsaleqty, 
                   Transactiondate, wantedtype
            FROM ordermanagement
            WHERE qtycheck = 1 
                  AND producttypename = @SelectedValue
                  AND storename = @storename
                  AND status = 0
                  AND orderqty > 0
            ORDER BY productname
        </sql>.Value
            )

            ' === Execute SQL and bind results to dgvMain ===
            Using connection As New SqlConnection(destinationConnectionString)
                Dim adapter As New SqlDataAdapter(query, connection)
                Dim builder As New SqlCommandBuilder(adapter)

                adapter.SelectCommand.Parameters.AddWithValue("@storename", storeName)
                If selectedValue <> "All" Then
                    adapter.SelectCommand.Parameters.AddWithValue("@SelectedValue", selectedValue)
                End If

                Dim dataSet As New DataSet()
                adapter.Fill(dataSet, "OrderManagement")

                ' Add Serial Number column
                Dim serialColumn As New DataColumn("SerialNo", GetType(Integer))
                dataSet.Tables("OrderManagement").Columns.Add(serialColumn)

                Dim serialNumber As Integer = 1
                For Each row As DataRow In dataSet.Tables("OrderManagement").Rows
                    row("SerialNo") = serialNumber
                    serialNumber += 1
                Next

                ' Temporarily remove the event handler to avoid reentrant calls
                RemoveHandler dgvMain.CellEnter, AddressOf dgvMain_CellEnter

                ' Bind to DataGridView
                dataSet.Tables("OrderManagement").Columns("SerialNo").SetOrdinal(0)

                dgvMain.DataSource = dataSet.Tables("OrderManagement")
                ConfigureDataGridViewnew(dgvMain)

                ' Re-enable the event handler
                AddHandler dgvMain.CellEnter, AddressOf dgvMain_CellEnter
            End Using

            ' === Focus first editable cell ===
            If dgvMain.Rows.Count > 0 Then
                dgvMain.CurrentCell = dgvMain.Rows(0).Cells(3)
            End If
            dgvMain.Focus()

        Catch ex As Exception
            ' Log detailed error to a file
            Dim logPath As String = "D:\OrderDotNet\Log\handling pending order.txt"
            Dim logMessage As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - " & ex.ToString()
            System.IO.File.AppendAllText(logPath, logMessage & Environment.NewLine)

            ' Show error message to user
            MessageBox.Show("An error occurred while handling pending order: " & ex.Message)
        End Try
    End Sub



    Private Sub txtSupplierSearch_KeyDown(sender As Object, e As KeyEventArgs) Handles txtSupplierSearch.KeyDown
        If e.KeyCode = Keys.Enter Then
            If txtSupplierSearch.Text = "Pending Order" Then
                dgvSupplierList.Visible = False
                HandlePendingOrder()
                dgvSupplierList.Visible = False
                UpdateDgvMainFooter()
                ResizeDgvMainFooterColumns()
                DgvMainFooter.Visible = True
                DgvMainFooter.Refresh()
                HandlePendingOrder()
            Else
                ' When Enter is pressed, focus and select first row in dgvSupplierList
                If dgvSupplierList.Rows.Count > 0 Then
                    dgvSupplierList.Focus()
                    dgvSupplierList.Rows(0).Selected = True
                End If
            End If
            e.SuppressKeyPress = True ' Prevents the "ding" sound
        ElseIf e.KeyCode = Keys.Escape Then
            ' When Escape is pressed, hide dgvSupplierList and clear the textbox
            dgvSupplierList.Visible = False
            txtSupplierSearch.Clear()
            txtSupplierSearch.Focus()
        ElseIf e.KeyCode = Keys.Down Then
            If txtSupplierSearch.Text = "Pending Order" Then
                dgvSupplierList.Visible = False
                HandlePendingOrder()
                dgvSupplierList.Visible = False
                UpdateDgvMainFooter()
                ResizeDgvMainFooterColumns()
                DgvMainFooter.Visible = True
                DgvMainFooter.Refresh()
                HandlePendingOrder()
            Else
                ' Otherwise show and focus dgvSupplierList
                If dgvSupplierList.Rows.Count > 0 Then
                    dgvSupplierList.Visible = True
                    dgvSupplierList.Focus()
                    dgvSupplierList.Rows(0).Selected = True
                End If
            End If
        End If
    End Sub


    Private Sub txtSupplierSearch_KeyPress(sender As Object, e As KeyPressEventArgs) Handles txtSupplierSearch.KeyPress
        If e.KeyChar = Convert.ToChar(Keys.Enter) Then
            If txtSupplierSearch.Text = "Pending Order" Then
                HandlePendingOrder()
                dgvSupplierList.Visible = False
                UpdateDgvMainFooter()
                ResizeDgvMainFooterColumns()
                DgvMainFooter.Visible = True
                DgvMainFooter.Refresh()

            Else
                dgvSupplierList.Visible = True
                dgvSupplierList.Select()
            End If

        ElseIf e.KeyChar = Convert.ToChar(Keys.Escape) Then
            dgvSupplierList.Visible = False
        End If
    End Sub

    Private Sub txtSupplierSearch_LostFocus(sender As Object, e As EventArgs) Handles txtSupplierSearch.LostFocus
        UpdateDgvMainFooter()
        ResizeDgvMainFooterColumns()
        DgvMainFooter.Visible = True
        DgvMainFooter.Refresh()
    End Sub

    Private Sub txtSupplierSearch_TextChanged(sender As Object, e As EventArgs) Handles txtSupplierSearch.TextChanged
        If txtSupplierSearch.Text = "Pending Order" Then
            dgvSupplierList.Visible = False
            Return
        Else
            dgvSupplierList.Visible = True
            dgvSupplierList.Location = New Point(472, 40)
        End If

        Dim query As String =
            <sql>
            SELECT UnifiedSupplierCODE, SupplierNAME
            FROM OrderSuppliers
            WHERE SupplierNAME LIKE @SupplierName AND storename = @storename
        </sql>.Value

        Using connection As New SqlConnection(destinationConnectionString)
            Try
                connection.Open()
                Using command As New SqlCommand(query, connection)
                    command.Parameters.AddWithValue("@SupplierName", txtSupplierSearch.Text & "%")
                    command.Parameters.AddWithValue("@storename", storeName)

                    Dim adapter As New SqlDataAdapter(command)
                    Dim table As New DataTable()
                    adapter.Fill(table)

                    dgvSupplierList.DataSource = table
                    dgvSupplierList.ReadOnly = True
                    dgvSupplierList.AllowUserToAddRows = False
                    dgvSupplierList.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.AllCells

                    ' Clear other displays
                    dgvPurchaseDetails.DataSource = Nothing
                    dgvSalesDetails.DataSource = Nothing
                    Chart1.Series.Clear()
                    Chart1.ChartAreas.Clear()
                End Using
            Catch ex As Exception
                MessageBox.Show("An error occurred while loading supplier data: " & ex.Message)
            End Try
        End Using
    End Sub

    Private Sub LoadDataForSupplierStock(supplierCode As String)
        ' ✅ Check if storeName is initialized
        If String.IsNullOrEmpty(storeName) Then
            MessageBox.Show("Store name is not set.", "Missing Data", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return
        End If

        Dim query As String =
            <sql>
        SELECT OM.productcode, 
               OM.productname, 
               OM.orderqty, 
               OM.totalstock, 
               SS.Stock AS S_Stock, 
               OM.slsqty, 
               OM.unitdescription, 
               OM.saleunit, 
               OM.mrp, 
               SS.discound, 
               SS.MINQTY, 
               ss.sch,
               ss.free, 
               SS.SupplierProductName, 
               SS.SupplierProductCode
        FROM OrderManagement OM
        INNER JOIN SupplierProductMatch SPM 
            ON OM.ProductCode = SPM.ProductCode 
           AND SPM.StoreName = OM.StoreName 
           AND SPM.SupplierCode = @suppliercode
        INNER JOIN SupplierStock SS 
            ON SS.SupplierProductCode = SPM.SupplierProductCode 
           AND SS.SupplierCode = @suppliercode and ss.storename=@storename
        WHERE OM.storename = @storename
          AND OM.status = 0
          AND OM.orderqty > 0
          AND SS.Stock > 0
        </sql>.Value

        ' Parameters for SQL query
        Dim parameters As New Dictionary(Of String, Object) From {
            {"@suppliercode", supplierCode},
            {"@storename", storeName}
        }

        query &= " ORDER BY OM.productname" ' Order the results by product name

        ' ✅ Wrap in try-catch for better diagnostics
        Try
            LoadDataGridView2(query, parameters)
        Catch ex As Exception
            MessageBox.Show("Failed to load data: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub



    ''' <summary>
    ''' Retrieves rack values for a list of product codes from the SupplierProductRack table.
    ''' </summary>
    ''' <param name="codes">List of product codes.</param>
    ''' <returns>Dictionary mapping code → combined rack values.</returns>
    Private Function GetRackValuesForCodes(codes As List(Of String)) As Dictionary(Of String, String)
        Dim rackValues As New Dictionary(Of String, String)()

        If String.IsNullOrWhiteSpace(destinationConnectionString) Then
            MessageBox.Show("Connection string is empty or invalid.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return rackValues
        End If

        If codes Is Nothing OrElse codes.Count = 0 Then
            Return rackValues
        End If

        ' Safely build IN clause
        Dim sanitizedCodes As New List(Of String)()
        For Each code As String In codes
            sanitizedCodes.Add("'" & code.Replace("'", "''") & "'")
        Next
        Dim codesList As String = String.Join(",", sanitizedCodes)
        MsgBox(suppliercode)
        ' Build query
        Dim query As String = "SELECT code, rack, rack1, rack2 FROM SupplierProductRack WHERE code IN (" & codesList & ") AND SUPPLIERCODE=" & suppliercode

        Try
            Using conn As New SqlConnection(destinationConnectionString)
                conn.Open()
                Using cmd As New SqlCommand(query, conn)
                    Using reader As SqlDataReader = cmd.ExecuteReader()
                        While reader.Read()
                            Dim code As String = reader("code").ToString()
                            Dim rack As String = If(IsDBNull(reader("rack")), "", reader("rack").ToString())
                            Dim rack1 As String = If(IsDBNull(reader("rack1")), "", reader("rack1").ToString())
                            Dim rack2 As String = If(IsDBNull(reader("rack2")), "", reader("rack2").ToString())

                            ' Combine non-empty rack values
                            Dim parts As New List(Of String)()
                            If rack <> "" Then parts.Add(rack)
                            If rack1 <> "" Then parts.Add(rack1)
                            If rack2 <> "" Then parts.Add(rack2)

                            Dim combinedRacks As String = String.Join(", ", parts)
                            rackValues(code) = combinedRacks
                        End While
                    End Using
                End Using
            End Using
        Catch ex As SqlException
            MessageBox.Show("SQL query error: " & ex.Message, "Database Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        Catch ex As Exception
            MessageBox.Show("Unexpected error: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try

        Return rackValues
    End Function

    Private Sub SelectOnlyRow(rowIndex As Integer)
        If cboProcess.SelectedItem IsNot Nothing AndAlso cboProcess.SelectedItem.ToString() = "Supplier Excel Mapping" Then
            Exit Sub
        End If
        If _manualCellNavigation Then Return ' << Skip if user is navigating
        If rowIndex < 0 OrElse rowIndex >= dgvMain.Rows.Count Then Exit Sub

        _suppressSelectionChange = True

        Try
            dgvMain.ClearSelection()

            Dim orderQtyColumnIndex As Integer = dgvMain.Columns("OrderQty").Index

            ' Only force focus to OrderQty if not already on 'free'
            If dgvMain.CurrentCell Is Nothing Then
                dgvMain.CurrentCell = dgvMain.Rows(rowIndex).Cells(orderQtyColumnIndex)
            End If

            dgvMain.Rows(rowIndex).Selected = True

        Catch ex As Exception
            File.AppendAllText("d:\OrderDotNet\Log Selection Only error.txt", Now.ToString() & " - Error: " & ex.ToString() & vbCrLf)
        Finally
            _suppressSelectionChange = False
        End Try
    End Sub



    Private Sub dgvPurchaseDetails_RowStateChanged(sender As Object, e As DataGridViewRowStateChangedEventArgs) Handles dgvPurchaseDetails.RowStateChanged
        ' Loop through all rows in the DataGridView
        For Each row As DataGridViewRow In dgvPurchaseDetails.Rows
            ' Ensure we skip any new rows (like empty rows for data entry)
            If Not row.IsNewRow Then
                ' Check if the value in the 'freeqty' column is greater than 0
                If Convert.ToDouble(row.Cells("freeqty").Value) > 0 Then
                    ' Change the row color to pink if the condition is met
                    row.DefaultCellStyle.BackColor = Color.DeepPink
                Else
                    ' Optionally reset the row color to default if condition is not met
                    row.DefaultCellStyle.BackColor = dgvPurchaseDetails.DefaultCellStyle.BackColor
                End If
            End If
        Next
    End Sub

    Private Sub ExportSelectedColumnsFromGrid(grid As DataGridView, filename As String)
        Using connection As New SqlConnection(destinationConnectionString)
            connection.Open()
            Dim selectedColumns As String() = {"ProductName", "OrderQty", "SaleUnit", "MRP", "ProductCode"}

            If grid.Rows.Count = 0 Then
                MessageBox.Show("No data in grid to export.")
                Exit Sub
            End If

            Dim orderNo As String = FetchOrderNo(connection)
            Dim excelApp As New Microsoft.Office.Interop.Excel.Application()
            Dim workbook As Microsoft.Office.Interop.Excel.Workbook = excelApp.Workbooks.Add()
            Dim worksheet As Microsoft.Office.Interop.Excel.Worksheet = workbook.Sheets("Sheet1")

            Dim totalCols As Integer = selectedColumns.Length + 1 ' +1 for S.No.

            ' Build data array large enough for all rows (will skip some later)
            Dim data(grid.Rows.Count + 1, totalCols - 1) As Object

            ' Set headers
            data(0, 0) = "S.No."
            For i = 0 To selectedColumns.Length - 1
                data(0, i + 1) = selectedColumns(i)
            Next

            ' Fill data only for rows where OrderQty ≠ 0
            Dim exportRowIndex As Integer = 1 ' Start from 1 since 0 is header
            For rowIndex As Integer = 0 To grid.Rows.Count - 1
                Dim orderQtyValue As Object = grid.Rows(rowIndex).Cells("OrderQty").Value
                Dim orderQtyDecimal As Decimal = 0

                If orderQtyValue IsNot Nothing Then
                    Dim expression As String = orderQtyValue.ToString().Trim()
                    If expression <> "" Then
                        Try
                            ' Evaluate the expression (e.g., "10+1")
                            Dim computedQty As Object = New DataTable().Compute(expression, "")
                            If Decimal.TryParse(computedQty.ToString(), orderQtyDecimal) AndAlso orderQtyDecimal <> 0 Then
                                ' Valid non-zero OrderQty, include this row
                                data(exportRowIndex, 0) = exportRowIndex ' S.No.
                                For colIndex As Integer = 0 To selectedColumns.Length - 1
                                    If grid.Columns.Contains(selectedColumns(colIndex)) Then
                                        Dim value = grid.Rows(rowIndex).Cells(selectedColumns(colIndex)).Value
                                        data(exportRowIndex, colIndex + 1) = If(value IsNot Nothing, value.ToString(), "")
                                    End If
                                Next
                                exportRowIndex += 1
                            End If
                        Catch ex As Exception
                            ' Ignore invalid expressions like "abc"
                        End Try
                    End If
                End If
            Next

            ' Adjust actual row count to written rows (excluding header)
            Dim actualRowCount As Integer = exportRowIndex - 1
            If actualRowCount = 0 Then
                MessageBox.Show("No rows with OrderQty <> 0 found.")
                excelApp.Quit()
                Exit Sub
            End If

            ' Write all at once to Excel
            Dim endCell As String = ChrW(Asc("A") + totalCols - 1).ToString() & (actualRowCount + 1).ToString()
            Dim writeRange As Microsoft.Office.Interop.Excel.Range = worksheet.Range("A1", endCell)
            writeRange.Value2 = data

            ' Auto-fit columns
            worksheet.Columns.AutoFit()

            ' Apply header formatting
            Dim headerRange As Microsoft.Office.Interop.Excel.Range = worksheet.Range("A1", worksheet.Cells(1, totalCols))
            With headerRange
                .Font.Bold = True
                .HorizontalAlignment = Microsoft.Office.Interop.Excel.XlHAlign.xlHAlignCenter
            End With

            ' Apply borders
            Dim usedRange As Microsoft.Office.Interop.Excel.Range = worksheet.Range("A1", worksheet.Cells(actualRowCount + 1, totalCols))
            With usedRange.Borders
                .LineStyle = Microsoft.Office.Interop.Excel.XlLineStyle.xlContinuous
                .Weight = Microsoft.Office.Interop.Excel.XlBorderWeight.xlThin
            End With

            ' Format columns
            Dim snoCol As Microsoft.Office.Interop.Excel.Range = worksheet.Range("A2", worksheet.Cells(actualRowCount + 1, 1))
            snoCol.HorizontalAlignment = Microsoft.Office.Interop.Excel.XlHAlign.xlHAlignCenter
            snoCol.Font.Bold = True
            snoCol.Interior.Color = System.Drawing.ColorTranslator.ToOle(Color.LightYellow)

            Dim orderQtyCol As Microsoft.Office.Interop.Excel.Range = worksheet.Range("C2", worksheet.Cells(actualRowCount + 1, 3))
            orderQtyCol.Interior.Color = System.Drawing.ColorTranslator.ToOle(Color.LightGreen)
            orderQtyCol.Font.Bold = True
            orderQtyCol.HorizontalAlignment = Microsoft.Office.Interop.Excel.XlHAlign.xlHAlignCenter

            Dim saleUnitCol As Microsoft.Office.Interop.Excel.Range = worksheet.Range("D2", worksheet.Cells(actualRowCount + 1, 4))
            saleUnitCol.Font.Color = System.Drawing.ColorTranslator.ToOle(Color.Gray)
            saleUnitCol.HorizontalAlignment = Microsoft.Office.Interop.Excel.XlHAlign.xlHAlignCenter

            Dim mrpCol As Microsoft.Office.Interop.Excel.Range = worksheet.Range("E2", worksheet.Cells(actualRowCount + 1, 5))
            mrpCol.Font.Color = System.Drawing.ColorTranslator.ToOle(Color.Gray)
            mrpCol.NumberFormat = "0.00"

            ' Save file logic
            Dim currentDate As DateTime = DateTime.Today
            Dim formattedDate As String = currentDate.ToString("ddMMyyyy")
            Dim folderPath1 As String = "D:\OrderDotNet\Export\"
            If Not Directory.Exists(folderPath1) Then Directory.CreateDirectory(folderPath1)
            Dim folderPath2 As String = Path.Combine(folderPath1, formattedDate)
            If Not Directory.Exists(folderPath2) Then Directory.CreateDirectory(folderPath2)
            folderPath2 &= "\"
            Dim folderPath3 As String = Path.Combine(folderPath2, orderNo)
            If Not Directory.Exists(folderPath3) Then Directory.CreateDirectory(folderPath3)

            Dim baseName As String = filename & " " & storeName & "   " & formattedDate
            Dim exportPath As String = Path.Combine(folderPath3, baseName & ".xlsx")
            Dim counter As Integer = 1
            While File.Exists(exportPath)
                exportPath = Path.Combine(folderPath3, baseName & "_" & counter.ToString() & ".xlsx")
                counter += 1
            End While

            workbook.SaveAs(exportPath)
            excelApp.Quit()

            MessageBox.Show("Selected grid columns exported to: " & exportPath)

            dgvMain.DataSource = Nothing
            txtSupplierSearch.Clear()
            HideAllComponents()
            cboProcess.Visible = True
            lblSelectProcess.Visible = True
            If cboProcess.Items.Count > 0 Then cboProcess.SelectedIndex = 0
            cboProcess.Focus()
        End Using
    End Sub

    Private Function FetchOrderNo(connection As SqlConnection) As String
        Dim orderNo As String = String.Empty
        Dim query As String = "SELECT MAX(OrderNo) AS OrderNo " & _
                              "FROM OrderHeaderDetails " & _
                              "WHERE CAST(OrderDateTime AS DATE) = CAST(GETDATE() AS DATE) " & _
                              "AND StoreName = @storename"

        Using command As New SqlCommand(query, connection)
            command.Parameters.AddWithValue("@storename", storeName)
            Dim result As Object = command.ExecuteScalar()
            If result IsNot Nothing AndAlso Not IsDBNull(result) Then
                orderNo = result.ToString()
            End If
        End Using

        Return orderNo
    End Function

    Private Sub btnExport_Click(sender As Object, e As EventArgs) Handles btnExport.Click
        ' Update the database (assuming this is a function to update the general data)
        UpdateDatabase()

        ' Check if the supplier search text is empty
        If String.IsNullOrWhiteSpace(txtSupplierSearch.Text) Then
            MessageBox.Show("Please enter a supplier name before exporting.", "Missing Input", MessageBoxButtons.OK, MessageBoxIcon.Warning)
            txtSupplierSearch.Focus()
            Exit Sub
        End If

        ' Call the function to export the selected columns
        ExportSelectedColumnsFromGrid(dgvMain, txtSupplierSearch.Text)

        ' Ensure suppliercode is set
        If Not String.IsNullOrEmpty(suppliercode) Then
            ' Loop through each row in the DataGridView
            For Each row As DataGridViewRow In dgvMain.Rows
                If Not row.IsNewRow Then
                    ' Get the supplierproductcode, OrderQty, and pack from the DataGridView
                    Dim supplierProductCode As String = row.Cells("supplierproductcode").Value.ToString()
                    Dim orderQty As Decimal = Convert.ToDecimal(row.Cells("Orderqty").Value)
                    Dim pack As Decimal = Convert.ToDecimal(row.Cells("pack").Value)

                    ' Calculate the new stock value
                    Dim query As String = "SELECT stock FROM supplierstock WHERE suppliercode = @Suppliercode AND supplierproductcode = @Supplierproductcode"

                    Using conn As New SqlConnection(destinationConnectionString)
                        Using cmd As New SqlCommand(query, conn)
                            ' Add parameters for suppliercode and supplierproductcode
                            cmd.Parameters.AddWithValue("@Suppliercode", suppliercode)
                            cmd.Parameters.AddWithValue("@Supplierproductcode", supplierProductCode)

                            ' Open the connection and retrieve the current stock value
                            conn.Open()
                            Dim currentStock As Decimal = Convert.ToDecimal(cmd.ExecuteScalar())

                            ' Calculate the new stock after subtracting OrderQty * pack
                            Dim newStock As Decimal = currentStock - (orderQty * pack)

                            ' Update the stock in the supplierstock table
                            Dim updateQuery As String = "UPDATE supplierstock SET stock = @NewStock WHERE suppliercode = @Suppliercode AND supplierproductcode = @Supplierproductcode"

                            Using updateCmd As New SqlCommand(updateQuery, conn)
                                ' Add parameters for updating the stock
                                updateCmd.Parameters.AddWithValue("@NewStock", newStock)
                                updateCmd.Parameters.AddWithValue("@Suppliercode", suppliercode)
                                updateCmd.Parameters.AddWithValue("@Supplierproductcode", supplierProductCode)

                                ' Execute the update query
                                updateCmd.ExecuteNonQuery()
                            End Using
                        End Using
                    End Using
                End If
            Next
        Else
            MessageBox.Show("Supplier code is not available.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End If
    End Sub


    Private Sub UpdateDatabase()
        Dim updateQuery As String = "UPDATE ordermanagement SET orqty = @orqty, orsupplier = @orsupplier, orsuppliercode = @orsuppliercode, status = 1 WHERE productcode = @productcode AND Orderqty > 0 and storename=@storename"

        Try
            Using connection As New SqlConnection(destinationConnectionString)
                connection.Open()

                For Each row As DataGridViewRow In dgvMain.Rows
                    If Not row.IsNewRow Then
                        Dim productCode As String = row.Cells(1).Value.ToString()
                        Dim orqty As Integer = Convert.ToInt32(row.Cells(3).Value)

                        ' Check if productCode exists in the database before updating
                        Dim checkQuery As String = "SELECT COUNT(*) FROM ordermanagement WHERE productcode = @productcode and storename=@storename"
                        Using checkCommand As New SqlCommand(checkQuery, connection)
                            checkCommand.Parameters.AddWithValue("@productcode", productCode)
                            checkCommand.Parameters.AddWithValue("@storename", storeName)
                            Dim rowCount As Integer = Convert.ToInt32(checkCommand.ExecuteScalar())

                            If rowCount > 0 Then
                                ' Product exists, proceed with update
                                Using command As New SqlCommand(updateQuery, connection)
                                    command.Parameters.AddWithValue("@orqty", orqty)

                                    If cboProcess.Text = "Pending Order" And txtSupplierSearch.Text = "Pending Order" Then
                                        command.Parameters.AddWithValue("@orsupplier", cboProcess.Text)
                                        command.Parameters.AddWithValue("@orsuppliercode", "pending")
                                    Else
                                        command.Parameters.AddWithValue("@orsupplier", txtSupplierSearch.Text)
                                        command.Parameters.AddWithValue("@orsuppliercode", suppliercode.ToString())
                                    End If

                                    command.Parameters.AddWithValue("@productcode", productCode)
                                    command.Parameters.AddWithValue("@Storename", storeName)
                                    command.ExecuteNonQuery()
                                End Using
                            Else

                                MessageBox.Show("Product with code '" & productCode & "' does not exist in the database.")
                            End If
                        End Using
                    End If
                Next
            End Using
        Catch ex As Exception
            ' Log the error to a file
            Dim logPath As String = "D:\OrderDotNet\Log\UpdateDatabaseError.txt"
            Dim logMessage As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - " & ex.ToString()
            System.IO.File.AppendAllText(logPath, logMessage & Environment.NewLine)

            ' Show error to user
            MessageBox.Show("Error updating database: " & ex.Message, "Database Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    Private Sub btnMapping_Click(sender As Object, e As EventArgs) Handles btnMapping.Click
        SaveMappingGridToDatabase()
        DGVMapping.DataSource = Nothing
        DGVMapping.Refresh()
        txtSupplierSearch.Clear()
        txtSupplierSearch.Visible = False
        lblSupplierName.Visible = False
        DGVMapping.Visible = False
        cboProcess.SelectedIndex = 0
        cboProcess.Focus()
    End Sub

    Private Sub btnExit_Click(sender As Object, e As EventArgs) Handles btnExit.Click
        End
    End Sub

    '--- Returns source SQL Server connection string
    Private Function BuildConnectionString(serverName As String, database As String, username As String, password As String) As String
        Return "Data Source=" & serverName & ";Initial Catalog=" & database & ";User ID=" & username & ";Password=" & password & ";Connect Timeout=60;"
    End Function

    Private Function FetchSourceData(connectionString As String, ODATA As String, storename As String, storecode As String, Optional reportProgress As Action(Of String) = Nothing) As DataTable
        If reportProgress IsNot Nothing Then reportProgress.Invoke("Connecting to source database...")

        Dim queryString As String = ""

        If RemoteDB.Checked Then
            ' Use source connection string for remote DB
            queryString = "WITH SalesQuantity AS (SELECT ps.productcode, SUM(ps.quantity) AS slsqty, COUNT(DISTINCT ps.ID) AS Frequence FROM ProductSaleInformation ps INNER JOIN products p ON ps.Productcode = p.productcode WHERE ps.Transactiondate >= @ODATA AND ps.quantity > 0 AND ps.SeriesTransID = 1 AND ps.transactionvalidity = 0 AND p.isactive = 1 AND ps.DontConsiderInOrder = 0 GROUP BY ps.productcode), ProductSaleInfo AS (SELECT p.productcode, p.productname, p.TotalStock, p.SaleUnit, sq.slsqty, p.PurchasePrice, p.MRP, p.UnitDescription, p.SubLocation, p.producttype, CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) AS AvgSalesQty, MAX(psi.Quantity) AS MaxSalesQtyInBill, GETDATE() AS wanteddate, @storename AS storename, @storecode AS storecode, CONVERT(VARCHAR(8), GETDATE(), 112) + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(MINUTE, GETDATE())), 2) + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(SECOND, GETDATE())), 2) AS OrderID, CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) < CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) THEN CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) ELSE CEILING((sq.slsqty / 90.0) * @minday) END AS minqty, CASE WHEN CEILING((sq.slsqty / 90.0) * @maxday) < MAX(psi.Quantity) THEN MAX(psi.Quantity) ELSE CEILING((sq.slsqty / 90.0) * @maxday) END AS maxqty, CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) <= T.Maxsaleqty THEN 'Single Day Sales Greater than MinQty' ELSE 'Regular Order Based Min & Max' END AS Wantedtype, sq.Frequence, l.lastsaledate, l.LastReceivedDate FROM products p INNER JOIN SalesQuantity sq ON p.productcode = sq.productcode LEFT JOIN ProductSaleInformation psi ON p.productcode = psi.Productcode AND psi.SeriesTransID = 1 AND psi.transactionvalidity = 0 AND psi.Transactiondate > @ODATA LEFT JOIN (SELECT Productcode, MAX(sales) AS Maxsaleqty FROM (SELECT SUM(Quantity) AS sales, Productcode FROM ProductSaleInformation WHERE SeriesTransID = 1 AND transactionvalidity = 0 AND Transactiondate > @ODATA GROUP BY Productcode) subquery GROUP BY Productcode) T ON p.productcode = T.Productcode LEFT JOIN (SELECT pt.Productcode, MAX(pt.LastBillDate) AS lastsaledate, MAX(pt.LastgrnDate) AS LastReceivedDate FROM ProductTrans pt WHERE pt.lastbilldate >= DATEADD(day, -20, GETDATE()) AND pt.LastBillDate IS NOT NULL GROUP BY Productcode) l ON p.productcode = l.Productcode GROUP BY p.productcode, p.productname, p.TotalStock, p.SaleUnit, sq.slsqty, p.PurchasePrice, p.MRP, p.UnitDescription, p.SubLocation, p.producttype, sq.Frequence, l.lastsaledate, l.LastReceivedDate, T.Maxsaleqty), MaxSaleInfo AS (SELECT T.Productcode, T.Maxsaleqty, T.Transactiondate FROM (SELECT Productcode, MAX(sales) AS Maxsaleqty, Transactiondate FROM (SELECT SUM(Quantity) AS sales, Productcode, Transactiondate, ROW_NUMBER() OVER(PARTITION BY Productcode ORDER BY SUM(Quantity) DESC) AS rn FROM ProductSaleInformation WHERE SeriesTransID = 1 AND transactionvalidity = 0 AND Transactiondate > @ODATA GROUP BY Productcode, Transactiondate) subquery WHERE rn = 1 GROUP BY Productcode, Transactiondate) T) SELECT ps.productcode, ps.productname, ps.minqty, ps.maxqty, ps.TotalStock, ps.slsqty, ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate, ps.wanteddate, ps.storename, ps.storecode, ps.OrderID, ps.SaleUnit, ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation, CASE WHEN ps.TotalStock = 0 AND ROUND(((ps.maxqty - ps.TotalStock) / ps.SaleUnit),0) = 0 THEN 'Rare Moment' WHEN CEILING(CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END) < m.Maxsaleqty THEN 'Min & Max Based MaxsaleQTY' WHEN ps.slsqty = m.Maxsaleqty AND m.Maxsaleqty = CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END AND ps.Frequence = 1 THEN 'Once Sold Last 90 days' ELSE 'Regular Order Based Min & Max' END AS Wantedtype, CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType, CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename, ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill, CASE WHEN ps.TotalStock = 0 AND CEILING(((ps.maxqty - ps.TotalStock) / ps.SaleUnit)) = 0 THEN 1 ELSE CEILING(((ps.maxqty - ps.TotalStock) / ps.SaleUnit)) END AS Orderqty, @status AS status FROM ProductSaleInfo ps LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode WHERE ps.lastsaledate >= DATEADD(day, -10, GETDATE()) AND (ps.maxqty - ps.TotalStock) / ps.SaleUnit > 0 AND ps.minqty > ps.TotalStock AND ps.lastsaledate >= ps.LastReceivedDate UNION ALL SELECT ps.productcode, ps.productname, 1 AS minqty, 1 AS maxqty, ps.TotalStock, ps.slsqty, ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate, ps.wanteddate, ps.storename, ps.storecode, ps.OrderID, ps.SaleUnit, ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation, 'Additional Row' AS Wantedtype, CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType2, CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename, ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill, 1 AS Orderqty, @status AS status FROM ProductSaleInfo ps LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode WHERE ps.TotalStock <= 1 AND ps.minqty <= 1 AND ps.Frequence > 1 AND ps.slsqty > 1 AND ps.lastsaledate >= DATEADD(day, -10, GETDATE()) AND ps.lastsaledate > ps.LastReceivedDate AND NOT EXISTS (SELECT 1 FROM ProductSaleInfo WHERE productcode = ps.productcode AND (ps.maxqty - ps.TotalStock) / ps.SaleUnit > 0 AND ps.minqty > ps.TotalStock) ORDER BY productname;"

        ElseIf LocalDB.Checked Then
            ' Use destination connection string for local DB
            queryString = "WITH SalesQuantity AS (SELECT ps.productcode, SUM(ps.quantity) AS slsqty, COUNT(DISTINCT ps.ID) AS Frequence, ps.storename FROM ProductSaleInformation ps INNER JOIN products p ON ps.Productcode = p.productcode AND ps.StoreName = p.StoreName WHERE ps.Transactiondate >= @ODATA AND ps.quantity > 0 AND ps.SeriesTransID = 1 AND ps.transactionvalidity = 0 AND p.isactive = 1 AND ps.DontConsiderInOrder = 0 AND ps.storename = @storename GROUP BY ps.productcode, ps.storename), MaxSalesQty AS (SELECT Productcode, MAX(Quantity) AS MaxSalesQtyInBill FROM ProductSaleInformation WHERE SeriesTransID = 1 AND transactionvalidity = 0 AND Transactiondate >= @ODATA AND storename = @storename GROUP BY Productcode), ProductSaleInfo AS (SELECT p.productcode, p.productname, p.TotalStock, p.SaleUnit, sq.slsqty, p.PurchasePrice, p.MRP, p.UnitDescription, p.SubLocation, p.producttype, CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) AS AvgSalesQty, m.MaxSalesQtyInBill, GETDATE() AS wanteddate, p.StoreName, @storecode AS storecode, CONVERT(VARCHAR(8), GETDATE(), 112) + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(MINUTE, GETDATE())), 2) + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(SECOND, GETDATE())), 2) AS OrderID, CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) < CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) THEN CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) ELSE CEILING((sq.slsqty / 90.0) * @minday) END AS minqty, CASE WHEN CEILING((sq.slsqty / 90.0) * @maxday) < m.MaxSalesQtyInBill THEN m.MaxSalesQtyInBill ELSE CEILING((sq.slsqty / 90.0) * @maxday) END AS maxqty, CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) <= maxQtyInPeriod.Maxsaleqty THEN 'Single Day Sales Greater than MinQty' ELSE 'Regular Order Based Min & Max' END AS Wantedtype, sq.Frequence, l.lastsaledate, l.LastReceivedDate FROM products p INNER JOIN SalesQuantity sq ON p.productcode = sq.productcode AND p.storename = sq.StoreName LEFT JOIN MaxSalesQty m ON p.productcode = m.Productcode LEFT JOIN (SELECT pt.Productcode, MAX(pt.LastBillDate) AS lastsaledate, MAX(pt.LastgrnDate) AS LastReceivedDate, pt.StoreName FROM ProductTrans pt WHERE pt.lastbilldate >= DATEADD(day, -20, GETDATE()) AND pt.LastBillDate IS NOT NULL AND pt.storename = @storename GROUP BY pt.Productcode, pt.StoreName) l ON p.productcode = l.Productcode LEFT JOIN (SELECT Productcode, MAX(sales) AS Maxsaleqty FROM (SELECT SUM(Quantity) AS sales, Productcode FROM ProductSaleInformation WHERE SeriesTransID = 1 AND transactionvalidity = 0 AND Transactiondate >= @ODATA AND storename = @storename GROUP BY Productcode) AS sales_summary GROUP BY Productcode) maxQtyInPeriod ON p.productcode = maxQtyInPeriod.Productcode), MaxSaleInfo AS (SELECT T.Productcode, T.Maxsaleqty, T.Transactiondate, T.storename FROM (SELECT Productcode, MAX(sales) AS Maxsaleqty, Transactiondate, storename FROM (SELECT SUM(Quantity) AS sales, Productcode, Transactiondate, psi.storename, ROW_NUMBER() OVER(PARTITION BY Productcode ORDER BY SUM(Quantity) DESC) AS rn FROM ProductSaleInformation psi WHERE psi.SeriesTransID = 1 AND psi.transactionvalidity = 0 AND psi.Transactiondate > @ODATA AND psi.storename = @storename GROUP BY Productcode, Transactiondate, psi.storename) subquery WHERE rn = 1 GROUP BY Productcode, Transactiondate, storename) T) SELECT ps.productcode, ps.productname, ps.minqty, ps.maxqty, ps.TotalStock, ps.slsqty, ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate, ps.wanteddate, ps.StoreName, @storecode AS storecode, ps.OrderID, ps.SaleUnit, ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation, CASE WHEN ps.TotalStock = 0 AND ROUND(((ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0)), 0) = 0 THEN 'Rare Moment' WHEN CEILING(CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END) < m.Maxsaleqty THEN 'Min & Max Based MaxsaleQTY' WHEN ps.slsqty = m.Maxsaleqty AND m.Maxsaleqty = CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END AND ps.Frequence = 1 THEN 'Once Sold Last 90 days' ELSE 'Regular Order Based Min & Max' END AS Wantedtype, CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType, CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename, ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill, CASE WHEN ps.TotalStock = 0 AND (ps.maxqty - ps.TotalStock) <= 0 THEN 1 WHEN ps.SaleUnit > 0 THEN CEILING((ps.maxqty - ps.TotalStock) / ps.SaleUnit) ELSE 0 END AS Orderqty, @status AS status FROM ProductSaleInfo ps LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode AND ps.StoreName = m.StoreName WHERE ps.lastsaledate >= DATEADD(day, -10, GETDATE()) AND (ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0) > 0 AND ps.minqty > ps.TotalStock AND ps.lastsaledate >= ps.LastReceivedDate AND ps.StoreName = @storename UNION ALL SELECT ps.productcode, ps.productname, 1 AS minqty, 1 AS maxqty, ps.TotalStock, ps.slsqty, ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate, ps.wanteddate, ps.StoreName, ps.storecode, ps.OrderID, ps.SaleUnit, ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation, 'Additional Row' AS Wantedtype, CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType2, CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename, ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill, 1 AS Orderqty, @status AS status FROM ProductSaleInfo ps LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode WHERE ps.TotalStock <= 1 AND ps.minqty <= 1 AND ps.Frequence > 1 AND ps.slsqty > 1 AND ps.lastsaledate >= DATEADD(day, -10, GETDATE()) AND ps.lastsaledate > ps.LastReceivedDate AND ps.StoreName = @storename AND NOT EXISTS (SELECT 1 FROM ProductSaleInfo WHERE productcode = ps.productcode AND (ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0) > 0 AND ps.minqty > ps.TotalStock AND storename = @storename) ORDER BY ps.productname;"
        Else
            queryString = ""

        End If

        If reportProgress IsNot Nothing Then reportProgress.Invoke("Preparing query and parameters...")

        Dim dataTable As New DataTable()
        Using connection As New SqlConnection(connectionString)
            Using command As New SqlCommand(queryString, connection)
                command.Parameters.AddWithValue("@minday", MinDays)
                command.Parameters.AddWithValue("@maxday", MaxDays)
                command.Parameters.AddWithValue("@storename", storename)
                command.Parameters.AddWithValue("@storecode", storecode)
                command.Parameters.AddWithValue("@ODATA", ODATA)
                command.Parameters.AddWithValue("@status", 0)
                command.CommandTimeout = 0

                connection.Open()

                If reportProgress IsNot Nothing Then reportProgress.Invoke("Executing query...")

                Using adapter As New SqlDataAdapter(command)
                    adapter.Fill(dataTable)
                End Using
            End Using
        End Using

        If reportProgress IsNot Nothing Then reportProgress.Invoke("Data fetched: " & dataTable.Rows.Count.ToString() & " rows.")

        Return dataTable
    End Function



    Private Sub InsertDataIntoDestination(dataTable As DataTable, storename As String)
        ' Last line of defence: never replace an HO-managed order set
        If IsIntegrationManagedStore(storename) Then
            Throw New InvalidOperationException("Order data for " & storename & " is managed by HO; local replacement blocked.")
        End If
        Dim destinationConnectionString As String = GetDestinationConnectionString()

        Using destinationSqlConnection As New SqlConnection(destinationConnectionString)
            destinationSqlConnection.Open()

            ' Step 1: Backup
            Dim backupCommand As New SqlCommand("INSERT INTO OrderManagementBackup SELECT * FROM OrderManagement WHERE StoreName = @StoreName", destinationSqlConnection)
            backupCommand.Parameters.AddWithValue("@StoreName", storename)
            backupCommand.ExecuteNonQuery()

            ' Step 2: Delete
            Dim deleteCommand As New SqlCommand("DELETE FROM OrderManagement WHERE StoreName = @StoreName", destinationSqlConnection)
            deleteCommand.Parameters.AddWithValue("@StoreName", storename)
            deleteCommand.ExecuteNonQuery()

            ' Step 3: Bulk Insert
            Using bulkCopy As New SqlBulkCopy(destinationSqlConnection)
                bulkCopy.DestinationTableName = "OrderManagement"
                ' Add your column mappings here
                bulkCopy.ColumnMappings.Add("productcode", "ProductCode")
                bulkCopy.ColumnMappings.Add("productname", "ProductName")
                bulkCopy.ColumnMappings.Add("TotalStock", "TotalStock")
                bulkCopy.ColumnMappings.Add("SaleUnit", "SaleUnit")
                bulkCopy.ColumnMappings.Add("slsqty", "SLSQty")
                bulkCopy.ColumnMappings.Add("PurchasePrice", "PurchasePrice")
                bulkCopy.ColumnMappings.Add("MRP", "MRP")
                bulkCopy.ColumnMappings.Add("UnitDescription", "UnitDescription")
                bulkCopy.ColumnMappings.Add("SubLocation", "SubLocation")
                bulkCopy.ColumnMappings.Add("producttype", "ProductType")
                bulkCopy.ColumnMappings.Add("LastReceivedDate", "LastReceivedDate")
                bulkCopy.ColumnMappings.Add("LastSaleDate", "LastSaleDate")
                bulkCopy.ColumnMappings.Add("MaxSaleQty", "MaxSaleQty")
                bulkCopy.ColumnMappings.Add("Transactiondate", "Transactiondate")
                bulkCopy.ColumnMappings.Add("WantedDate", "WantedDate")
                bulkCopy.ColumnMappings.Add("storename", "StoreName")
                bulkCopy.ColumnMappings.Add("StoreCode", "StoreCode")
                bulkCopy.ColumnMappings.Add("OrderId", "OrderId")
                bulkCopy.ColumnMappings.Add("MinQty", "MinQty")
                bulkCopy.ColumnMappings.Add("MaxQty", "MaxQty")
                bulkCopy.ColumnMappings.Add("WantedType", "WantedType")
                bulkCopy.ColumnMappings.Add("OrderQty", "OrderQty")
                bulkCopy.ColumnMappings.Add("OrderQty", "OrgOrderQty")
                bulkCopy.ColumnMappings.Add("productTypeName", "ProductTypeName")
                bulkCopy.ColumnMappings.Add("Frequence", "Frequence")
                bulkCopy.ColumnMappings.Add("Status", "Status")
                bulkCopy.WriteToServer(dataTable)
            End Using

            ' Step 4: Update Additional Rows
            Dim updateCommand As New SqlCommand("UPDATE OrderManagement SET OrderQty = 0, OrgOrderQty = 0, Status = 2, Remarks = 'Additional' WHERE StoreName = @StoreName AND WantedType = 'Additional Row'", destinationSqlConnection)
            updateCommand.Parameters.AddWithValue("@StoreName", storename)
            updateCommand.ExecuteNonQuery()
        End Using
    End Sub

    Private Sub UpdateOrderHeaderDetails()
        ' Uses global MinDays and MaxDays, and txtStoreSearch for store name
        Dim sourceConnectionString As String = BuildConnectionString(serverName, database, username, password)

        ' Get Last Sale Bill Info
        Dim lastSaleBillNo As String = ""
        Dim lastBillDateTime As DateTime = DateTime.MinValue
        Using connection As New SqlConnection(sourceConnectionString)
            connection.Open()
            Using command As New SqlCommand("SELECT TOP 1 Transactiondate, BNumber FROM ProductSaleInformation WHERE BNumber LIKE 'C%' ORDER BY Transactiondate DESC, BNumber DESC", connection)
                Using reader As SqlDataReader = command.ExecuteReader()
                    If reader.Read() Then
                        lastSaleBillNo = reader("BNumber").ToString()
                        If Not IsDBNull(reader("Transactiondate")) Then
                            lastBillDateTime = Convert.ToDateTime(reader("Transactiondate"))
                        End If
                    End If
                End Using
            End Using
        End Using

        ' Get Last GRN
        Dim lastGRN As String = ""
        Using connection As New SqlConnection(sourceConnectionString)
            connection.Open()
            Using command As New SqlCommand("SELECT TOP 1 Grnnumber FROM Purchasetrans where InvoiceSeries = 'IV' ORDER BY Grndate DESC", connection)
                Using reader As SqlDataReader = command.ExecuteReader()
                    If reader.Read() Then
                        lastGRN = reader("Grnnumber").ToString()
                    End If
                End Using
            End Using
        End Using

        ' Get Order Info from OrderManagement
        Dim orderNo As Integer = 1
        Dim orderid As Long = 0
        Dim orstorename As String = ""
        Dim wantedDate As DateTime = DateTime.MinValue

        Using connection As New SqlConnection(destinationConnectionString)
            connection.Open()
            Dim sqlQuery As String = "SELECT TOP 1 WantedDate, OrderId, StoreName FROM OrderManagement WHERE StoreName = @StoreName ORDER BY OrderId DESC"
            Using command As New SqlCommand(sqlQuery, connection)
                command.Parameters.AddWithValue("@StoreName", txtStoreSearch.Text.Trim())
                Using reader As SqlDataReader = command.ExecuteReader()
                    If reader.Read() Then
                        If Not IsDBNull(reader("WantedDate")) Then
                            wantedDate = Convert.ToDateTime(reader("WantedDate"))
                        Else
                            Return
                        End If
                        orstorename = reader("StoreName").ToString()
                        orderid = Convert.ToInt64(reader("OrderId"))
                    Else
                        Return
                    End If
                End Using
            End Using

            If wantedDate < New DateTime(1753, 1, 1) Or wantedDate > New DateTime(9999, 12, 31) Then
                Return
            End If

            Dim todayDate As DateTime = Date.Today
            Using command As New SqlCommand("SELECT COUNT(*) FROM OrderHeaderDetails WHERE StoreName=@StoreName AND CONVERT(date, OrderDateTime) = @TodayDate", connection)
                command.Parameters.AddWithValue("@TodayDate", todayDate)
                command.Parameters.AddWithValue("@StoreName", orstorename)
                Dim count As Integer = Convert.ToInt32(command.ExecuteScalar())
                If count > 0 Then
                    orderNo = count + 1
                Else
                    orderNo = 1
                End If
            End Using

            Using command As New SqlCommand("INSERT INTO OrderHeaderDetails (StoreName, OrderId, OrderNo, OrderDateTime, LastSaleBillNo, LastBillDateTime, LastGRN, MinDays, MaxDays) VALUES (@StoreName, @OrderId, @OrderNo, @OrderDateTime, @LastSaleBillNo, @LastBillDateTime, @LastGRN, @MinDays, @MaxDays)", connection)
                command.Parameters.AddWithValue("@OrderId", orderid)
                command.Parameters.AddWithValue("@StoreName", orstorename)
                command.Parameters.AddWithValue("@OrderNo", orderNo)
                command.Parameters.AddWithValue("@OrderDateTime", wantedDate)
                command.Parameters.AddWithValue("@LastSaleBillNo", lastSaleBillNo)
                command.Parameters.AddWithValue("@LastBillDateTime", If(lastBillDateTime = DateTime.MinValue, DBNull.Value, lastBillDateTime))
                command.Parameters.AddWithValue("@LastGRN", lastGRN)
                command.Parameters.AddWithValue("@MinDays", MinDays)
                command.Parameters.AddWithValue("@MaxDays", MaxDays)
                command.ExecuteNonQuery()
            End Using
        End Using
    End Sub

   Private Sub ProcessOrder()
        If IsIntegrationManagedStore(storeName) Then
            MessageBox.Show("Orders for " & storeName & " are managed by HO. Local order generation is disabled.", "Process Order", MessageBoxButtons.OK, MessageBoxIcon.Information)
            Exit Sub
        End If
        If String.IsNullOrEmpty(serverName) OrElse String.IsNullOrEmpty(username) OrElse
           String.IsNullOrEmpty(password) OrElse String.IsNullOrEmpty(database) OrElse
           String.IsNullOrEmpty(storeName) Then
            MessageBox.Show("Source DB not Connected", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Exit Sub
        End If

        ProgressBar1.Visible = True
        ProgressBar1.Style = ProgressBarStyle.Marquee
        lblstatus.Visible = True
        lblstatus.Text = "Starting order data fetch..."

        BackgroundWorker1.RunWorkerAsync(WorkerTask.FetchOrderData)
    End Sub


    Private Sub dgvMain_CellFormatting(sender As Object, e As DataGridViewCellFormattingEventArgs) Handles dgvMain.CellFormatting
        Dim dgv As DataGridView = CType(sender, DataGridView)
        If dgv.CurrentCell Is Nothing Then Exit Sub

        Dim colName As String = dgv.Columns(e.ColumnIndex).Name
        Dim isFocused As Boolean = (dgv.CurrentCell.RowIndex = e.RowIndex AndAlso dgv.CurrentCell.ColumnIndex = e.ColumnIndex)

        If isFocused Then
            Dim logLine As String = "[" & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & "] CellFormatting: Row " & e.RowIndex.ToString() &
                                    ", Col " & colName & " - IsFocused: True" & Environment.NewLine
            System.IO.File.AppendAllText("d:\OrderDotNet\Log\CellFormattingLog.txt", logLine)
        End If
    End Sub

    Private Sub dgvMain_CurrentCellChanged(sender As Object, e As EventArgs) Handles dgvMain.CurrentCellChanged
        If dgvMain.CurrentCell Is Nothing Then Exit Sub

        Dim rowIndex As Integer = dgvMain.CurrentCell.RowIndex
        Dim colIndex As Integer = dgvMain.CurrentCell.ColumnIndex
        Dim colName As String = dgvMain.Columns(colIndex).Name
        Dim log As String = "[" & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & "] CurrentCellChanged: Row=" & rowIndex.ToString() & ", Col=" & colName

        System.IO.File.AppendAllText("d:\OrderDotNet\Log\CurrentCellChanged.txt", log & Environment.NewLine)
    End Sub

    Private Sub SetupDgvMainFooter()
        DgvMainFooter.Columns.Clear()
        DgvMainFooter.Rows.Clear()

        With DgvMainFooter
            .ColumnCount = 10
            .Columns(0).Name = "LabelUser"
            .Columns(1).Name = "ValueUser"
            .Columns(2).Name = "LabelDate"
            .Columns(3).Name = "ValueDate"
            .Columns(4).Name = "LabelDay"
            .Columns(5).Name = "ValueDay"
            .Columns(6).Name = "LabelTime"
            .Columns(7).Name = "ValueTime"
            .Columns(8).Name = "LabelTotalProducts"
            .Columns(9).Name = "ValueTotalProducts"

            ' Optional styling
            .RowHeadersVisible = False
            .AllowUserToAddRows = False
            .AllowUserToDeleteRows = False
            .AllowUserToResizeRows = False
            .AllowUserToResizeColumns = False
            .ReadOnly = True
            .ColumnHeadersVisible = False
            .DefaultCellStyle.BackColor = Color.LightYellow
            .Rows.Add()
        End With

        If DgvMainFooter.Rows.Count > 0 Then
            With DgvMainFooter.Rows(0).DefaultCellStyle
                .Font = New Font("Segoe UI", 10, FontStyle.Bold)
                .ForeColor = Color.DarkBlue
                .BackColor = Color.Beige
                .Alignment = DataGridViewContentAlignment.MiddleLeft
            End With
        End If
        DgvMainFooter.ClearSelection()
        DgvMainFooter.Rows(0).Selected = False
        DgvMainFooter.Enabled = False ' Optional: disables keyboard focus
    End Sub


    Private Sub UpdateDgvMainFooter()
        If DgvMainFooter.Rows.Count = 0 Then Exit Sub

        Dim row = DgvMainFooter.Rows(0)

        row.Cells("LabelUser").Value = "User Name:"
        row.Cells("ValueUser").Value = UserSession.UserName

        row.Cells("LabelDate").Value = "Date:"
        row.Cells("ValueDate").Value = DateTime.Now.ToString("dd-MM-yyyy")

        row.Cells("LabelDay").Value = "Day:"
        row.Cells("ValueDay").Value = DateTime.Now.ToString("dddd")

        row.Cells("LabelTime").Value = "Time:"
        row.Cells("ValueTime").Value = DateTime.Now.ToString("hh:mm tt")

        row.Cells("LabelTotalProducts").Value = "Total Products:"
        row.Cells("ValueTotalProducts").Value = dgvMain.Rows.Count.ToString()
    End Sub

    Private Sub ResizeDgvMainFooterColumns()
        DgvMainFooter.Columns("LabelUser").Width = 100
        DgvMainFooter.Columns("ValueUser").Width = 80
        DgvMainFooter.Columns("LabelDate").Width = 60
        DgvMainFooter.Columns("ValueDate").Width = 100
        DgvMainFooter.Columns("LabelDay").Width = 50
        DgvMainFooter.Columns("ValueDay").Width = 100
        DgvMainFooter.Columns("LabelTime").Width = 50
        DgvMainFooter.Columns("ValueTime").Width = 120
        DgvMainFooter.Columns("LabelTotalProducts").Width = 120
        DgvMainFooter.Columns("ValueTotalProducts").AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill
    End Sub

    Private Sub footerTimer_Tick(sender As Object, e As EventArgs) Handles footerTimer.Tick
        If DgvMainFooter.Rows.Count = 0 Then Exit Sub
        DgvMainFooter.Rows(0).Cells("ValueTime").Value = DateTime.Now.ToString("hh:mm:ss tt")
    End Sub


    Private Sub btnExportJson_Click(sender As Object, e As EventArgs) Handles btnExportJson.Click
        If Not IsWebExportAllowed() Then Exit Sub
        ' ExportOrderSuppliersToJson()
        ExportDgvMainToJson()
    End Sub


    Public Sub CreateModifiedJsonList()
        Dim dataPath As String = "D:\VBDOTNet\OrderManagement\webOrder\data\"
        Dim outputFilePath As String = Path.Combine(dataPath, "modified_files.json")
        Dim today As Date = Date.Today
        Dim modifiedList As New List(Of ModifiedFile)

        For Each filePath As String In Directory.GetFiles(dataPath, "*.json")
            Dim fileName As String = Path.GetFileName(filePath)
            Dim modDate As Date = File.GetLastWriteTime(filePath).Date

            If modDate = today AndAlso Not fileName.Equals("modified_files.json", StringComparison.OrdinalIgnoreCase) Then
                modifiedList.Add(New ModifiedFile With {
                    .filename = fileName,
                    .lastModified = modDate.ToString("yyyy-MM-dd")
                })
            End If
        Next

        ' Serialize and save the list
        Dim json As String = JsonConvert.SerializeObject(modifiedList, Formatting.Indented)
        File.WriteAllText(outputFilePath, json)

        MessageBox.Show("Modified JSON list saved to: " & outputFilePath)
    End Sub

    Public Class ModifiedFile
        Public Property filename As String
        Public Property lastModified As String
    End Class

    Public Sub PullJsonFromGitHub()
        Dim jsonUrl As String = "https://api.render.com/deploy/srv-d1dchs95pdvs73alfn4g?key=ct490IS80mc"
        Dim localDirectory As String = "D:\VBDOTNet\OrderManagement\webOrder\data\pull\"
        Dim localFilePath As String = Path.Combine(localDirectory, "yourfile.json")

        Try
            ' Ensure the local directory exists
            If Not Directory.Exists(localDirectory) Then
                Directory.CreateDirectory(localDirectory)
            End If

            ' Download using WebClient
            Using client As New Net.WebClient()
                client.DownloadFile(jsonUrl, localFilePath)
            End Using

            MessageBox.Show("JSON file downloaded successfully to: " & localFilePath)

        Catch ex As Exception
            MessageBox.Show("Error downloading JSON file: " & ex.Message)
        End Try
    End Sub

    Public Sub PullTodaysFilesFromList()

        System.Net.ServicePointManager.SecurityProtocol = System.Net.SecurityProtocolType.Tls12

        Dim baseUrl As String = "https://api.render.com/deploy/srv-d1dchs95pdvs73alfn4g?key=ct490IS80mc"
        Dim localDirectory As String = "D:\VBDOTNet\OrderManagement\webOrder\data\pull\"
        Dim logDirectory As String = "D:\OrderDotNet\Log\"
        Dim logFilePath As String = Path.Combine(logDirectory, "pull_" & DateTime.Now.ToString("yyyyMMdd") & ".log")
        Dim indexFileUrl As String = baseUrl & "modified_files.json"
        Dim tempIndexPath As String = Path.Combine(localDirectory, "modified_files.json")

        Try
            ' Ensure required directories exist
            If Not Directory.Exists(localDirectory) Then Directory.CreateDirectory(localDirectory)
            If Not Directory.Exists(logDirectory) Then Directory.CreateDirectory(logDirectory)

            ' Download modified_files.json
            Using client As New Net.WebClient()
                client.DownloadFile(indexFileUrl, tempIndexPath)
            End Using

            Dim json As String = File.ReadAllText(tempIndexPath)
            Dim modifiedList = JsonConvert.DeserializeObject(Of List(Of ModifiedFile))(json)

            For Each item In modifiedList
                Dim remoteFileUrl As String = baseUrl & item.filename
                Dim localPath As String = Path.Combine(localDirectory, item.filename)

                Try
                    Using client As New Net.WebClient()
                        client.DownloadFile(remoteFileUrl, localPath)
                    End Using
                Catch ex As Exception
                    Dim err As String = "[" & Now.ToString("yyyy-MM-dd HH:mm:ss") & "] ❌ Error downloading " & item.filename & ": " & ex.Message
                    File.AppendAllText(logFilePath, err & Environment.NewLine)
                End Try
            Next

            Dim successMsg As String = "[" & Now.ToString("yyyy-MM-dd HH:mm:ss") & "] ✅ All listed files processed successfully."
            File.AppendAllText(logFilePath, successMsg & Environment.NewLine)
            MessageBox.Show("✅ All listed files downloaded.")

        Catch ex As Exception
            Dim err As String = "[" & Now.ToString("yyyy-MM-dd HH:mm:ss") & "] ❌ Error pulling file list: " & ex.Message
            File.AppendAllText(logFilePath, err & Environment.NewLine)
            MessageBox.Show("❌ Error pulling file list: " & ex.Message)
        End Try
    End Sub



    Private Sub ExportDgvMainToJson()
        If String.IsNullOrWhiteSpace(suppliercode) Then
            MessageBox.Show("Supplier code is missing.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            txtSupplierSearch.Focus()
            Exit Sub
        End If

        Try
            Dim exportDir As String = "d:\VBDOTNet\OrderManagement\webOrder\data"
            If Not Directory.Exists(exportDir) Then Directory.CreateDirectory(exportDir)

            ' === Export JSON ===
            Dim ordersList As New List(Of Dictionary(Of String, Object))()
            For Each row As DataGridViewRow In dgvMain.Rows
                If Not row.IsNewRow Then
                    ' === Skip if OrQty <= 0 ===

                    Dim orQtyObj As Object = row.Cells("OrderQty").Value
                    Dim orQty As Decimal
                    If orQtyObj Is Nothing OrElse Not Decimal.TryParse(orQtyObj.ToString(), orQty) OrElse orQty <= 0 Then
                        Continue For
                    End If

                    Dim orderItem As New Dictionary(Of String, Object)()

                    For Each col As DataGridViewColumn In dgvMain.Columns
                        Dim colName As String = col.Name
                        Dim colValue As Object = row.Cells(colName).Value
                        orderItem(colName) = If(colValue IsNot Nothing, colValue.ToString(), "")
                    Next

                    Dim productCode As String = row.Cells("ProductCode").Value.ToString()
                    Dim orderInfo = GetOrderDetailsFromDB(productCode, storeName)
                    If orderInfo IsNot Nothing Then
                        orderItem("OrderId") = orderInfo("OrderId")
                        orderItem("StoreName") = orderInfo("StoreName")
                        orderItem("StoreCode") = orderInfo("StoreCode")
                    Else
                        orderItem("OrderId") = ""
                        orderItem("StoreName") = ""
                        orderItem("StoreCode") = ""
                    End If

                    orderItem("suppliername") = txtSupplierSearch.Text.Trim()
                    orderItem("productName") = row.Cells("Productname").Value.ToString()
                    ordersList.Add(orderItem)
                End If
            Next

            ' === Safe filename
            Dim safeStoreName As String = New String(storeName.Where(Function(c) Not Path.GetInvalidFileNameChars().Contains(c)).ToArray())
            Dim jsonFileName As String = safeStoreName & "_" & suppliercode & ".json"
            Dim jsonPath As String = Path.Combine(exportDir, jsonFileName)

            ' === Write to file
            Dim jsonOutput As String = JsonConvert.SerializeObject(ordersList, Formatting.Indented)
            File.WriteAllText(jsonPath, jsonOutput, Encoding.UTF8)

            ' === Update users.json ===
            Dim usersPath As String = Path.Combine(exportDir, "users.json")
            Dim users As New List(Of Dictionary(Of String, String))()
            If File.Exists(usersPath) Then
                Dim existingJson As String = File.ReadAllText(usersPath)
                users = JsonConvert.DeserializeObject(Of List(Of Dictionary(Of String, String)))(existingJson)
            End If

            Dim existingUser = users.FirstOrDefault(Function(u) u("suppliercode") = suppliercode)
            If existingUser Is Nothing Then
                ' Add new user with StoreName
                users.Add(New Dictionary(Of String, String) From {
                    {"username", suppliercode},
                    {"password", "pass"},
                    {"suppliercode", suppliercode},
                    {"suppliername", txtSupplierSearch.Text.Trim()},
                    {"GSTNumber", "Test"},
                    {"StoreName", storeName}
                })
            Else
                ' Update existing user with StoreName
                existingUser("suppliername") = txtSupplierSearch.Text.Trim()
                existingUser("GSTNumber") = "Test"
                existingUser("StoreName") = storeName ' Added StoreName here
            End If
            File.WriteAllText(usersPath, JsonConvert.SerializeObject(users, Formatting.Indented), Encoding.UTF8)

            ' === Create storeheader.json if needed
            Dim storeHeaderPath As String = Path.Combine(exportDir, "storeheader.json")
            If Not File.Exists(storeHeaderPath) Then CreateStoreHeaderJson(exportDir)

            lblstatus.Visible = True
            lblstatus.Text = "Export complete. Pushing to GitHub..."
            Application.DoEvents()

            ' === Push and redeploy
            PushExportToGitHub(exportDir, jsonFileName)
            ForceGitHubRedeploy()

            lblstatus.Text = "Export + Push complete."
            MessageBox.Show("Exported and pushed successfully.", "Done", MessageBoxButtons.OK, MessageBoxIcon.Information)

        Catch ex As Exception
            lblstatus.Text = "Error during export"
            MessageBox.Show("Export failed: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub


    Private Sub PushExportToGitHub(exportPath As String, exportedJsonFile As String)
        Dim repoPath As String = "d:\VBDOTNet\OrderManagement\webOrder\"
        Dim logDir As String = "d:\OrderDotNet\Log\"
        Dim logFilePath As String = Path.Combine(logDir, "Githuberror.txt")

        If Not Directory.Exists(logDir) Then Directory.CreateDirectory(logDir)

        lblstatus.Text = "Pushing to GitHub..."
        lblstatus.Visible = True

        Dim dataPath As String = Path.Combine(repoPath, "data")

        ' Step 1: Define always-keep files
        Dim filesToAlwaysKeep As New HashSet(Of String)(StringComparer.OrdinalIgnoreCase) From {
            "users.json",
            "storeheader.json",
            "ordersuppliers.json"
        }

        ' Step 2: Build filesToKeep with today's modified JSON files + always-keep
        Dim today As Date = Date.Today
        Dim filesToKeep As New HashSet(Of String)(filesToAlwaysKeep, StringComparer.OrdinalIgnoreCase)

        If Directory.Exists(dataPath) Then
            For Each filePath As String In Directory.GetFiles(dataPath, "*.json")
                Dim fileName As String = Path.GetFileName(filePath)
                Dim fileDate As Date = File.GetLastWriteTime(filePath).Date
                If fileDate = today Then
                    filesToKeep.Add(fileName)
                End If
            Next
        End If

        ' Step 3: Delete files not in the keep list
        If Directory.Exists(dataPath) Then
            For Each filePath As String In Directory.GetFiles(dataPath)
                Dim fileName As String = Path.GetFileName(filePath)
                If Not filesToKeep.Contains(fileName) Then
                    Try
                        File.Delete(filePath)
                    Catch ex As Exception
                        File.AppendAllText(logFilePath, vbCrLf & "Failed to delete " & fileName & ": " & ex.Message)
                    End Try
                End If
            Next
        End If

        ' Step 4: Git commit and push
        Dim psi As New ProcessStartInfo With {
            .FileName = "cmd.exe",
            .WorkingDirectory = repoPath,
            .RedirectStandardInput = True,
            .RedirectStandardOutput = True,
            .RedirectStandardError = True,
            .UseShellExecute = False,
            .CreateNoWindow = True
        }

        Using process As New Process With {.StartInfo = psi}
            process.Start()

            Using sw As StreamWriter = process.StandardInput
                If sw.BaseStream.CanWrite Then
                    sw.WriteLine("git config core.autocrlf false")

                    ' ✅ Force dummy file update
                    File.AppendAllText(Path.Combine(repoPath, "README.md"), vbCrLf & " ")

                    ' ✅ Stage changes and commit
                    sw.WriteLine("git add -A")
                    Dim commitMsg As String = "Updated: " & exportedJsonFile & " at " & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                    sw.WriteLine("git commit -m """ & commitMsg & """")
                    sw.WriteLine("git pull --rebase origin main")
                    sw.WriteLine("git push origin main")
                End If
            End Using


            Dim output As String = process.StandardOutput.ReadToEnd()
            Dim errorOut As String = process.StandardError.ReadToEnd()
            process.WaitForExit()

            If Not String.IsNullOrWhiteSpace(errorOut) AndAlso errorOut.ToLower().Contains("error") Then
                lblstatus.Text = "Git Push Error"
                File.AppendAllText(logFilePath, vbCrLf & "=== [" & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & "] Git Error ===" & vbCrLf & errorOut & vbCrLf)
                MessageBox.Show("Git Push Error occurred. See log at: " & logFilePath, "Git Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Else
                lblstatus.Text = "Pushed successfully"
                TriggerRenderDeployHook() ' ✅ Auto trigger Render deployment here
            End If

        End Using
    End Sub


    Public Sub ForceGitHubRedeploy()
        Dim repoPath As String = "D:\VBDOTNET\OrderManagement\WebOrder"
        Dim readmePath As String = Path.Combine(repoPath, "README.md")
        File.AppendAllText(readmePath, vbCrLf & " ") ' Dummy change to force commit
        Dim gitCommands As String() = {
            "git add README.md",
            "git commit -m ""Trigger redeploy " & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & """",
            "git push origin main"
        }
        For Each cmd As String In gitCommands
            RunGitCommand(repoPath, cmd)
        Next


        ' 🔁 Trigger Render Deployment Hook after GitHub push
        TriggerRenderDeployHook()
        lblstatus.Text = "Redeploy triggered"

    End Sub

    Private Sub TriggerRenderDeployHook()
        Try
            ' ✅ Force TLS 1.2 (required for Render's HTTPS endpoint)
            System.Net.ServicePointManager.SecurityProtocol = System.Net.SecurityProtocolType.Tls12

            Dim request As Net.HttpWebRequest = CType(Net.WebRequest.Create("https://api.render.com/deploy/srv-d1dchs95pdvs73alfn4g?key=ct490IS80mc"), Net.HttpWebRequest)
            request.Method = "GET"

            Using response As Net.HttpWebResponse = CType(request.GetResponse(), Net.HttpWebResponse)
                If response.StatusCode = Net.HttpStatusCode.OK Then
                    lblstatus.Text = "Deploy triggered via Render hook"
                Else
                    lblstatus.Text = "Deploy hook responded with status: " & response.StatusCode.ToString()
                End If
            End Using
        Catch ex As Exception
            File.AppendAllText("D:\OrderDotNet\Log\DeployHookError.txt", vbCrLf & DateTime.Now.ToString() & ": " & ex.Message)
            MessageBox.Show("Deploy Hook Failed: " & ex.Message, "Deploy Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub




    Private Sub RunGitCommand(repoPath As String, command As String)
        Dim psi As New ProcessStartInfo With {
            .FileName = "cmd.exe",
            .WorkingDirectory = repoPath,
            .Arguments = "/C " & command,
            .UseShellExecute = False,
            .CreateNoWindow = True,
            .RedirectStandardOutput = True,
            .RedirectStandardError = True
        }
        Using process As New Process With {.StartInfo = psi}
            process.Start()
            Dim output As String = process.StandardOutput.ReadToEnd()
            Dim errorOut As String = process.StandardError.ReadToEnd()
            process.WaitForExit()
            If Not String.IsNullOrWhiteSpace(errorOut) Then
                ' Optional: log the full error for review
                Dim logFile As String = Path.Combine("D:\OrderDotNet\Log\", "GitCommandErrorLog.txt")
                File.AppendAllText(logFile, vbCrLf & "=== [" & DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & "] ===" & vbCrLf & errorOut & vbCrLf)

                ' Show it in a message box
                MessageBox.Show("Git Error: " & errorOut, "Git Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            End If

        End Using
    End Sub


    Private Sub ExportOrderSuppliersToJson()
        lblstatus.Visible = True
        lblstatus.Text = "Starting export of OrderSuppliers..."
        Application.DoEvents()

        Dim exportDir As String = "d:\VBDOTNet\OrderManagement\webOrder\data"
        Dim jsonFileName As String = "OrderSuppliers.json"
        Dim jsonPath As String = Path.Combine(exportDir, jsonFileName)

        If Not Directory.Exists(exportDir) Then Directory.CreateDirectory(exportDir)

        ' STEP 1: Read from OrderSuppliers
        Dim dt As New DataTable()
        Try
            lblstatus.Text = "Fetching data from database..."
            Application.DoEvents()

            Using conn As New SqlConnection(destinationConnectionString)
                conn.Open()
                Using cmd As New SqlCommand("SELECT * FROM OrderSuppliers", conn)
                    Using da As New SqlDataAdapter(cmd)
                        da.Fill(dt)
                    End Using
                End Using
            End Using
        Catch ex As Exception
            lblstatus.Text = "DB Error"
            MessageBox.Show("Failed to fetch data from OrderSuppliers: " & ex.Message, "DB Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Exit Sub
        End Try

        ' STEP 2: Convert to List(Of Dictionary)
        Dim dataList As New List(Of Dictionary(Of String, Object))()
        For Each row As DataRow In dt.Rows
            Dim dict As New Dictionary(Of String, Object)()
            For Each col As DataColumn In dt.Columns
                dict(col.ColumnName) = row(col.ColumnName)
            Next
            dataList.Add(dict)
        Next

        ' STEP 3: Write JSON
        Try
            lblstatus.Text = "Writing JSON file..."
            Application.DoEvents()

            Dim jsonOutput As String = JsonConvert.SerializeObject(dataList, Formatting.Indented)
            File.WriteAllText(jsonPath, jsonOutput, Encoding.UTF8)
        Catch ex As Exception
            lblstatus.Text = "Write Error"
            MessageBox.Show("Failed to write JSON: " & ex.Message, "File Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Exit Sub
        End Try

        ' STEP 4: Git Push
        lblstatus.Text = "Pushing to GitHub..."
        Application.DoEvents()

        PushExportToGitHub(exportDir, jsonFileName)


        ' STEP 5: Trigger redeploy
        lblstatus.Text = "Triggering redeploy..."
        Application.DoEvents()
        ForceGitHubRedeploy()

        lblstatus.Text = "Export & push completed."
        MessageBox.Show("OrderSuppliers.json exported and pushed successfully!", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information)
    End Sub



    Private Sub CreateStoreHeaderJson(exportDir As String)
        Dim storesList As New List(Of Dictionary(Of String, String))()
        ' Fetch store details from the stores table
        Dim storeDetails = GetStoreDetailsFromDB()
        If storeDetails IsNot Nothing Then
            For Each store In storeDetails
                Dim storeItem As New Dictionary(Of String, String)()
                storeItem("StoreCode") = store("StoreCode").ToString()
                storeItem("StoreName") = store("StoreName").ToString()
                storeItem("StoreFullName") = store("StoreFullName").ToString()
                storeItem("Address1") = store("Address1").ToString()
                storeItem("Address2") = store("Address2").ToString()
                storesList.Add(storeItem)
            Next
        End If
        ' Write store details to JSON file
        Dim jsonOutput As String = JsonConvert.SerializeObject(storesList, Formatting.Indented)
        File.WriteAllText(Path.Combine(exportDir, "storeheader.json"), jsonOutput, Encoding.UTF8)
    End Sub


    Private Function GetStoreDetailsFromDB() As List(Of Dictionary(Of String, Object))
        ' Implement this function to fetch store details from the database
        Dim connection As New SqlConnection(destinationConnectionString)
        Dim command As New SqlCommand("SELECT StoreCode, StoreName, StoreFullName, Address1, Address2 FROM Stores where isactive=1", connection)
        connection.Open()
        Dim reader As SqlDataReader = command.ExecuteReader()
        Dim storesList As New List(Of Dictionary(Of String, Object))()
        While reader.Read()
            Dim store As New Dictionary(Of String, Object)()
            store("StoreCode") = reader("StoreCode")
            store("StoreName") = reader("StoreName")
            store("StoreFullName") = reader("StoreFullName")
            store("Address1") = reader("Address1")
            store("Address2") = reader("Address2")
            storesList.Add(store)
        End While
        reader.Close()
        connection.Close()
        Return storesList
    End Function

    Private Function GetOrderDetailsFromDB(productCode As String, storeName As String) As Dictionary(Of String, Object)
        Dim result As New Dictionary(Of String, Object)
        Dim query As String = "SELECT TOP 1 OrderId, StoreName, StoreCode FROM OrderManagement " &
                              "WHERE ProductCode = @ProductCode AND StoreName = @StoreName"
        Using conn As New SqlConnection(destinationConnectionString)
            Using cmd As New SqlCommand(query, conn)
                cmd.Parameters.AddWithValue("@ProductCode", productCode)
                cmd.Parameters.AddWithValue("@StoreName", storeName)
                conn.Open()
                Using reader As SqlDataReader = cmd.ExecuteReader()
                    If reader.Read() Then
                        result("OrderId") = reader("OrderId").ToString()
                        result("StoreName") = reader("StoreName").ToString()
                        result("StoreCode") = reader("StoreCode").ToString()
                        Return result
                    End If
                End Using
            End Using
        End Using
        Return Nothing ' Not found
    End Function

    Private Sub LoadOrderIDSupplier()
        Dim todayDate As String = DateTime.Now.ToString("yyyy-MM-dd")
        Dim query As String = "SELECT DISTINCT TOP 10 " & _
                              "OMB.storename, " & _
                              "OMB.orderid, " & _
                              "OHD.OrderNo, " & _
                              "OMB.WantedDate, " & _
                              "COUNT(CASE WHEN OMB.ProductType = 1 THEN 1 END) AS Pharma_Products, " & _
                              "COUNT(CASE WHEN OMB.ProductType != 1 THEN 1 END) AS Non_Pharma_Products, " & _
                              "COUNT(CASE WHEN OMB.Status = 1 THEN 1 END) AS Order_Placed " & _
                              "FROM OrderManagementBackup OMB " & _
                              "INNER JOIN OrderHeaderDetails OHD ON OMB.orderid = OHD.orderid " & _
                              "WHERE OMB.storename = @storename " & _
                              "GROUP BY OMB.storename, OMB.orderid, OHD.OrderNo, OMB.WantedDate " & _
                              "HAVING COUNT(CASE WHEN OMB.Status = 1 THEN 1 END) > 0 " & _
                              "ORDER BY OMB.WantedDate DESC"

        Using conn As New SqlConnection(destinationConnectionString)
            Using cmd As New SqlCommand(query, conn)
                cmd.Parameters.AddWithValue("@storename", storename)

                Dim adapter As New SqlDataAdapter(cmd)
                Dim table As New DataTable()

                conn.Open()
                adapter.Fill(table)
                conn.Close()

                dgvSupplierList.DataSource = table
                dgvSupplierList.Visible = True
                dgvSupplierList.AutoSize = True
                dgvSupplierList.Focus()
            End Using
        End Using
    End Sub

    Private Sub LoadDistinctOrSuppliers(storeName As String, orderId As Double)
        Dim query As String = "SELECT " & vbCrLf & _
                              "    OrSupplierCode, " & vbCrLf & _
                              "    OrSupplier, " & vbCrLf & _
                              "    COUNT(ProductCode) AS ProductCount " & vbCrLf & _
                              "FROM OrderManagementBackup " & vbCrLf & _
                              "WHERE StoreName = @StoreName " & vbCrLf & _
                              "  AND OrderID = @OrderID " & vbCrLf & _
                              "  AND ISNULL(LTRIM(RTRIM(OrSupplier)), '') <> '' " & vbCrLf & _
                              "  AND ISNULL(LTRIM(RTRIM(OrSupplierCode)), '') <> '' " & vbCrLf & _
                              "GROUP BY OrSupplier, OrSupplierCode " & vbCrLf & _
                              "ORDER BY OrSupplier"


        Using conn As New SqlConnection(destinationConnectionString)
            Using cmd As New SqlCommand(query, conn)
                cmd.Parameters.AddWithValue("@StoreName", storeName)
                cmd.Parameters.AddWithValue("@OrderID", orderId)

                Dim adapter As New SqlDataAdapter(cmd)
                Dim table As New DataTable()

                conn.Open()
                adapter.Fill(table)
                conn.Close()

                ' Bind to DataGridView
                DGVMapping.DataSource = table
                DGVMapping.Visible = True
                DGVMapping.ReadOnly = False
                DGVMapping.AllowUserToAddRows = False
                DGVMapping.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.None
                DGVMapping.EditMode = DataGridViewEditMode.EditOnEnter
                DGVMapping.Width = 400

                ' Set custom column widths
                If DGVMapping.Columns.Contains("OrSupplierCode") Then
                    DGVMapping.Columns("OrSupplierCode").Visible = True
                    DGVMapping.Columns("OrSupplierCode").Width = 60
                End If
                If DGVMapping.Columns.Contains("OrSupplier") Then
                    DGVMapping.Columns("OrSupplier").Width = 280
                End If
                If DGVMapping.Columns.Contains("ProductCount") Then
                    DGVMapping.Columns("ProductCount").Width = 60
                End If

                DGVMapping.Focus()
            End Using
        End Using

    End Sub


    Private Sub Form1_FormClosed(sender As Object, e As FormClosedEventArgs) Handles Me.FormClosed
        Application.Exit()
    End Sub

    Private Sub DGVMapping_SelectionChanged(sender As Object, e As EventArgs) Handles DGVMapping.SelectionChanged
        If DGVMapping.CurrentRow Is Nothing OrElse DGVMapping.CurrentRow.IsNewRow Then Exit Sub
        If DGVMapping.CurrentRow.Cells("OrSupplierCode").Value Is DBNull.Value Then Exit Sub

        DGVMapping.CurrentRow.Selected = True

        Dim selectedOrSupplierCode As String = DGVMapping.CurrentRow.Cells("OrSupplierCode").Value.ToString()
        Dim storeName As String = txtStoreSearch.Text.Trim()
        Dim orderId As Double = SelectedOrderId ' Replace with your actual global variable
        dgvMain.DataSource = Nothing

        Dim query As String = "SELECT " & vbCrLf & _
                              "    o.ProductCode as code, " & vbCrLf & _
                              "    o.ProductName as name, " & vbCrLf & _
                              "    ISNULL(o.OrderQty, '') as OrderQty, " & vbCrLf & _
                              "    ISNULL(o.WantedType, '') AS WantedType, " & vbCrLf & _
                              "    b.ProductCode, " & vbCrLf & _
                              "    b.ProductName, " & vbCrLf & _
                              "    b.OrQty, " & vbCrLf & _
                              "    b.Remarks, " & vbCrLf & _
                              "    b.status " & vbCrLf & _
                              "FROM OrderManagementBackup b " & vbCrLf & _
                              "LEFT JOIN OrderManagement o ON " & vbCrLf & _
                              "    b.ProductCode = o.ProductCode AND " & vbCrLf & _
                              "    o.StoreName = b.StoreName " & vbCrLf & _
                              "WHERE " & vbCrLf & _
                              "    b.StoreName = @StoreName " & vbCrLf & _
                              "    AND b.OrderID = @OrderID " & vbCrLf & _
                              "    AND b.OrSupplierCode = @OrSupplierCode " & vbCrLf & _
                              "ORDER BY o.ProductName desc ;"

        Using conn As New SqlConnection(destinationConnectionString)
            Using cmd As New SqlCommand(query, conn)
                cmd.Parameters.AddWithValue("@StoreName", storeName)
                cmd.Parameters.AddWithValue("@OrderID", orderId)
                cmd.Parameters.AddWithValue("@OrSupplierCode", selectedOrSupplierCode)

                Dim adapter As New SqlDataAdapter(cmd)
                Dim table As New DataTable()

                conn.Open()
                adapter.Fill(table)
                conn.Close()

                ' Add serial number column
                table.Columns.Add("SNo", GetType(Integer))
                For i As Integer = 0 To table.Rows.Count - 1
                    table.Rows(i)("SNo") = i + 1
                Next

                ' Set SNo as the first column
                table.Columns("SNo").SetOrdinal(0)

                ' Bind to dgvMain
                dgvMain.DataSource = table

                ' Position dgvMain to the right of DGVMapping
                dgvMain.Top = DGVMapping.Top
                dgvMain.Left = DGVMapping.Right + 10
                dgvMain.Width = Me.ClientSize.Width - dgvMain.Left - 10
                dgvMain.Height = DGVMapping.Height

                dgvMain.Visible = True
                '  dgvMain.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill
                '  dgvMain.EditMode = DataGridViewEditMode.EditOnEnter
                ConfigureDataGridViewnew(dgvMain)
                dgvMain.Refresh()
            End Using
        End Using
    End Sub

    Private Sub CompareOrderManagementSupplierWise(orderId As Double, storeName As String, orSupplierCode As String)
        Dim query As String =
            "UPDATE om SET " & vbCrLf &
            "    om.orqty = omb.orqty, " & vbCrLf &
            "    om.orsupplier = omb.orsupplier, " & vbCrLf &
            "    om.status = 2, " & vbCrLf &
            "    om.remarks = @remarks " & vbCrLf &
            "FROM OrderManagement om " & vbCrLf &
            "INNER JOIN OrderManagementBackup omb ON om.productcode = omb.productcode " & vbCrLf &
            "WHERE omb.orderid = @orderid " & vbCrLf &
            "  AND (omb.status = 1 OR omb.status = 0) " & vbCrLf &
            "  AND om.storename = @storename " & vbCrLf &
            "  AND omb.orsuppliercode = @orsuppliercode " & vbCrLf &
            "  AND ( " & vbCrLf &
            "       (omb.totalstock > om.totalstock AND om.storename = omb.storename) " & vbCrLf &
            "       OR (omb.status = 1 OR omb.orderqty = 0) " & vbCrLf &
            "  ); " & vbCrLf & vbCrLf &
            "UPDATE om SET " & vbCrLf &
            "    om.orderqty = (om.Orgorderqty - omb.orqty), " & vbCrLf &
            "    om.status = 0, " & vbCrLf &
            "    om.remarks = 'After Order Sold', " & vbCrLf &
            "    om.wantedtype = 'After Order Sold' " & vbCrLf &
            "FROM OrderManagement om " & vbCrLf &
            "INNER JOIN OrderManagementBackup omb ON om.productcode = omb.productcode " & vbCrLf &
            "WHERE omb.orderid = @orderid " & vbCrLf &
            "  AND om.storename = @storename " & vbCrLf &
            "  AND omb.orsuppliercode = @orsuppliercode " & vbCrLf &
            "  AND omb.totalstock > om.totalstock " & vbCrLf &
            "  AND om.storename = omb.storename " & vbCrLf &
            "  AND (om.orderqty - omb.orqty) > 0;"

        Try
            Using conn As New SqlConnection(destinationConnectionString)
                Using cmd As New SqlCommand(query, conn)
                    cmd.Parameters.AddWithValue("@orderid", orderId)
                    cmd.Parameters.AddWithValue("@remarks", "Compare Supplier " & orSupplierCode & " with Order ID: " & orderId)
                    cmd.Parameters.AddWithValue("@storename", storeName)
                    cmd.Parameters.AddWithValue("@orsuppliercode", orSupplierCode)

                    conn.Open()
                    Dim affectedRows = cmd.ExecuteNonQuery()
                    MessageBox.Show("Supplier comparison complete. Updated rows: " & affectedRows, "Success", MessageBoxButtons.OK, MessageBoxIcon.Information)
                End Using
            End Using
        Catch ex As Exception
            MessageBox.Show("Error in supplier-wise comparison: " & ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    Private Sub btnCompareSelectedSupplier_Click(sender As Object, e As EventArgs) Handles btnCompareSelectedSupplier.Click
        If DGVMapping.CurrentRow Is Nothing Then
            MessageBox.Show("Please select a supplier first.", "Missing Selection", MessageBoxButtons.OK, MessageBoxIcon.Warning)
            Exit Sub
        End If

        Dim orSupplierCode As String = DGVMapping.CurrentRow.Cells("OrSupplierCode").Value.ToString()
        Dim storeName As String = txtStoreSearch.Text.Trim()
        Dim orderId As Double = SelectedOrderId

        CompareOrderManagementSupplierWise(orderId, storeName, orSupplierCode)
    End Sub

    Private Sub Syncbtn_Click(sender As Object, e As EventArgs) Handles Syncbtn.Click
        If String.IsNullOrEmpty(txtStoreSearch.Text) Then
            MessageBox.Show("Store Name cannot be empty.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            txtStoreSearch.Focus()
            Exit Sub
        End If
        If IsIntegrationManagedStore(txtStoreSearch.Text.Trim()) Then
            MessageBox.Show("Data for " & txtStoreSearch.Text.Trim() & " is synchronised automatically by the NMV Sync Agent." & vbCrLf & "Manual Sync is not available for this store.", "Sync", MessageBoxButtons.OK, MessageBoxIcon.Information)
            Exit Sub
        End If
        currentStoreName = txtStoreSearch.Text
        sourceConnectionString = BuildConnectionString(serverName, database, username, password)
        Try
            Using conn As New SqlConnection(sourceConnectionString)
                conn.Open()
            End Using
        Catch ex As Exception
            MessageBox.Show("Failed to connect to the database." & vbCrLf & ex.Message, "Connection Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            txtStoreSearch.Focus()
            Exit Sub
        End Try
        tablesToSync = New List(Of Tuple(Of String, String)) From {
            Tuple.Create("Products", "Products"),
            Tuple.Create("SaleInformation", "SaleInformation"),
            Tuple.Create("ProductTrans", "ProductTrans"),
            Tuple.Create("PurchaseTrans", "PurchaseTrans"),
            Tuple.Create("ProductSaleInformation", "ProductSaleInformation"),
            Tuple.Create("SalesRep", "SalesRep"),
            Tuple.Create("Suppliers", "OrderSuppliers"),
            Tuple.Create("Batches", "Batches"),
            Tuple.Create("SupplierProductMatch", "SupplierProductMatch")
        }
        lblstatus.Visible = True
        ProgressBar1.Visible = True
        ProgressBar1.Minimum = 0
        ProgressBar1.Maximum = tablesToSync.Count
        ProgressBar1.Value = 0
        lblStatus.Text = "Starting sync..."
        BackgroundWorker1.WorkerReportsProgress = True
        BackgroundWorker1.RunWorkerAsync()
    End Sub

     Private Sub BackgroundWorker1_DoWork(sender As Object, e As DoWorkEventArgs) Handles BackgroundWorker1.DoWork
        Dim taskType As WorkerTask = CType(e.Argument, WorkerTask)

        If taskType = WorkerTask.SyncTables Then
            ' Existing sync logic
            Dim rowCount As Integer = 0
            For i As Integer = 0 To tablesToSync.Count - 1
                Dim t = tablesToSync(i)
                Try
                    BackgroundWorker1.ReportProgress(i, "Starting sync: " & t.Item1)
                    rowCount = CentralSyncHelper.SyncTable(sourceConnectionString, destinationConnectionString, t.Item1, t.Item2, currentStoreName)
                    BackgroundWorker1.ReportProgress(i + 1, "Completed: " & t.Item1 & " (" & rowCount.ToString() & " rows)")
                Catch ex As Exception
                    BackgroundWorker1.ReportProgress(i + 1, "Error syncing " & t.Item1 & ": " & ex.Message)
                End Try
            Next

        ElseIf taskType = WorkerTask.FetchOrderData Then
            Dim ODATA As String = Date.Today.AddDays(-90).ToString("yyyy-MM-dd")
            Dim sourceConnection As String = If(RemoteDB.Checked, BuildConnectionString(serverName, database, username, password), destinationConnectionString)

            ' Callback for updating UI text
            Dim report As Action(Of String) = Sub(msg)
                                                  BackgroundWorker1.ReportProgress(0, msg)
                                              End Sub

            BackgroundWorker1.ReportProgress(0, "Fetching data from source...")

            Dim dt As DataTable = FetchSourceData(sourceConnection, ODATA, storeName, storeCode, report)

            ' Save to result to access in RunWorkerCompleted
            e.Result = dt
        End If
    End Sub



    Private Sub CallSmartSyncMerge(connString As String, tableName As String, storeName As String)
        Try
            Using conn As New SqlConnection(connString)
                Using cmd As New SqlCommand("usp_SmartSyncMerge", conn)
                    cmd.CommandType = CommandType.StoredProcedure
                    cmd.Parameters.AddWithValue("@TableName", tableName)
                    cmd.Parameters.AddWithValue("@StoreName", storeName)

                    conn.Open()
                    cmd.CommandTimeout = 300   ' optional: prevent timeout for large tables
                    cmd.ExecuteNonQuery()
                End Using
            End Using
        Catch ex As Exception
            ' Log or show message for specific procedure errors
            BackgroundWorker1.ReportProgress(0, "⚠️ Merge failed for " & tableName & ": " & ex.Message)
        End Try
    End Sub


    Private Sub BackgroundWorker1_ProgressChanged(sender As Object, e As ProgressChangedEventArgs) Handles BackgroundWorker1.ProgressChanged
        ' Update ProgressBar
        If e.ProgressPercentage > 0 AndAlso ProgressBar1.Maximum >= e.ProgressPercentage Then
            ProgressBar1.Value = e.ProgressPercentage
        End If

        ' Update label and log
        If TypeOf e.UserState Is String Then
            Dim msg As String = CStr(e.UserState)
            lblstatus.Text = msg

            ' Append to log file
            Try
                Dim logFile As String = "D:\VBDOTNET\OrderManagement\Log\sync.log"
                Dim logLine As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - " & msg & Environment.NewLine
                System.IO.File.AppendAllText(logFile, logLine)
            Catch ex As Exception
                ' Optional: ignore or handle logging error
            End Try
        End If
    End Sub



    Private Sub BackgroundWorker1_RunWorkerCompleted(sender As Object, e As RunWorkerCompletedEventArgs) Handles BackgroundWorker1.RunWorkerCompleted
        ProgressBar1.Visible = False
        lblstatus.Visible = False

        If e.Error IsNot Nothing Then
            MessageBox.Show("Error: " & e.Error.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return
        End If

        If TypeOf e.Result Is DataTable Then
            ' Order data fetch result
            Dim dt As DataTable = CType(e.Result, DataTable)
            InsertDataIntoDestination(dt, storeName)
            UpdateOrderHeaderDetails()
            Me.Text = "All Data Copied"
            MessageBox.Show("Order processing completed!", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information)
        Else
            ' Table sync finished
            lblstatus.Text = "Sync completed."
            MessageBox.Show("All tables synced successfully.", "Done", MessageBoxButtons.OK, MessageBoxIcon.Information)
        End If
    End Sub


    Private Function IsValidDatePassword(inputPassword As String) As Boolean
        ' Get current date details
        Dim currentDate As DateTime = DateTime.Today

        ' Get parts of the date
        Dim dayOfWeek As Integer = CType(currentDate.DayOfWeek, Integer) + 1 ' Sunday = 1, Saturday = 7
        Dim month As String = currentDate.Month.ToString("D2")
        Dim day As String = currentDate.Day.ToString("D2")

        ' Build dynamic password (M2D2DOWD1M1)
        Dim M2 As Char = month(1)
        Dim D2 As Char = day(1)
        Dim DOW As String = dayOfWeek.ToString()
        Dim D1 As Char = day(0)
        Dim M1 As Char = month(0)

        Dim generatedPassword As String = M2 & D2 & DOW & D1 & M1

        ' Compare with input
        Return inputPassword = generatedPassword
    End Function

    Private Sub LogDailyActivity(message As String)
        Try
            Dim logFolder As String = "D:\OrderDotNet\Log\OrderChanges"
            If Not Directory.Exists(logFolder) Then Directory.CreateDirectory(logFolder)

            Dim fileName As String = "OrderChange_" & DateTime.Now.ToString("yyyy-MM-dd") & ".log"
            Dim logFilePath As String = Path.Combine(logFolder, fileName)
            Dim logLine As String = DateTime.Now.ToString("HH:mm:ss") & " - " & message & Environment.NewLine

            File.AppendAllText(logFilePath, logLine)
        Catch ex As Exception
            MessageBox.Show("Log write failed: " & ex.Message)
        End Try
    End Sub

    Private dgvMainLogFilePath As String = ""

    Private Sub InitNewDgvMainLogFile()
        Dim logDir As String = "D:\OrderDotNet\Log\dgvMain"
        If Not Directory.Exists(logDir) Then Directory.CreateDirectory(logDir)

        Dim timestamp As String = DateTime.Now.ToString("yyyy-MM-dd_HHmmss")
        Dim fileName As String = "dgvMain_" & timestamp & ".log"
        dgvMainLogFilePath = Path.Combine(logDir, fileName)
    End Sub

    Private Sub LogToDgvMainFile(message As String)
        Try
            If String.IsNullOrEmpty(dgvMainLogFilePath) Then InitNewDgvMainLogFile()

            Dim logEntry As String = DateTime.Now.ToString("HH:mm:ss") & " - " & message & Environment.NewLine
            File.AppendAllText(dgvMainLogFilePath, logEntry)
        Catch ex As Exception
            MessageBox.Show("Failed to write dgvMain log: " & ex.Message)
        End Try
    End Sub

    Private Sub LogDgvMainFullContents()
        Try
            InitNewDgvMainLogFile() ' create new file for this load

            ' Log filter controls
            LogToDgvMainFile("=== dgvMain Load Triggered ===")
            LogToDgvMainFile("StoreSearch: " & txtStoreSearch.Text)
            LogToDgvMainFile("Process: " & cboProcess.Text)
            LogToDgvMainFile("ProductType: " & cboProductType.Text)
            LogToDgvMainFile("Select: " & cboSelect.Text)
            LogToDgvMainFile("SupplierSearch: " & txtSupplierSearch.Text)

            LogToDgvMainFile("=== dgvMain Column Headers ===")
            Dim columnHeaders As String = ""
            For Each col As DataGridViewColumn In dgvMain.Columns
                If col.Visible Then
                    columnHeaders &= col.HeaderText & vbTab
                End If
            Next
            LogToDgvMainFile(columnHeaders.Trim())

            LogToDgvMainFile("=== dgvMain Load Start ===")

            ' Log each row's values
            For i As Integer = 0 To dgvMain.Rows.Count - 1
                Dim row As DataGridViewRow = dgvMain.Rows(i)
                If Not row.IsNewRow Then
                    Try
                        Dim line As String = "Row " & (i + 1).ToString() & ": "
                        For Each col As DataGridViewColumn In dgvMain.Columns
                            If col.Visible Then
                                Dim val As String = ""
                                Try
                                    val = If(row.Cells(col.Index).Value IsNot Nothing, row.Cells(col.Index).Value.ToString(), "")
                                Catch ex As Exception
                                    val = "ERROR"
                                End Try
                                line &= val & vbTab
                            End If
                        Next
                        LogToDgvMainFile(line.TrimEnd())
                    Catch ex As Exception
                        LogToDgvMainFile("Row " & (i + 1).ToString() & ": Error reading row - " & ex.Message)
                    End Try
                End If
            Next

            LogToDgvMainFile("=== dgvMain Load End ===")

        Catch ex As Exception
            LogToDgvMainFile("Error during LogDgvMainFullContents: " & ex.Message)
        End Try
    End Sub


    ' Web Export (GitHub/Render supplier portal) would deliver orders a second way for an HO-managed store.
    ' Allowed only when nmv_integration_store.AllowWebExport = 1 for that store.
    Private Function IsWebExportAllowed() As Boolean
        Dim managedStore As Boolean, webExportAllowed As Boolean
        GetIntegrationFlags(storeName, managedStore, webExportAllowed)
        If managedStore AndAlso Not webExportAllowed Then
            MessageBox.Show("Orders for " & storeName & " are sent to HO by the NMV Sync Agent." & vbCrLf & "Web Export is disabled for this store to avoid duplicate order delivery.", "Web Export", MessageBoxButtons.OK, MessageBoxIcon.Information)
            Return False
        End If
        Return True
    End Function

    Private Sub Button1_Click(sender As Object, e As EventArgs) Handles Button1.Click
        If Not IsWebExportAllowed() Then Exit Sub
        CreateModifiedJsonList()
        PushExportToGitHub("data", "modified_files.json")
        PullTodaysFilesFromList()
    End Sub
End Class
