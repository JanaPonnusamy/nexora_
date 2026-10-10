using System;
using System.Windows.Forms;

namespace NexoraOrderManagement
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            var cfg = AppConfig.Load();
            using (var login = new LoginForm(cfg))
            {
                if (login.ShowDialog() != DialogResult.OK || login.Api == null)
                    return;
                Application.Run(new MainForm(cfg, login.Api));
            }
        }
    }
}
