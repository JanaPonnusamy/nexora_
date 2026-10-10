namespace NexoraOrderManagement
{
    // Raised by a screen when the selected product row changes, so the shell can
    // refresh the shared right-hand detail panel.
    internal delegate void ProductSelectedHandler(long productCode, string productName);
}
