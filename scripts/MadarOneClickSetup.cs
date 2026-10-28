// Single-file GUI installer. The signed-by-nobody Windows .exe holds an
// appended ZIP with a customer package and offline WebView2 prerequisite.
// It never removes user profile data or launches the actual customer app.
using System;
using System.IO;
using System.IO.Compression;
using System.Diagnostics;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class MadarOneClickSetup {
    [STAThread]
    private static int Main(string[] args) {
        Application.EnableVisualStyles();
        bool qa = args.Length == 4 && args[0] == "--qa-isolated";
        try {
            if (args.Length != 0 && !qa) throw new Exception("Invalid command line.");
            string qaRoot = qa ? Path.GetFullPath(args[1]) : null;
            if (qa && (!Directory.Exists(qaRoot) || !File.Exists(Path.Combine(qaRoot, ".madar-qa-marker"))))
                throw new Exception("Isolated QA folder must exist and be explicitly marked.");
            if (!qa && MessageBox.Show(
                "Madar Desk 1.0.1 will be installed for this Windows account.\n" +
                "Existing Madar data will be preserved. Close Madar before continuing.\n" +
                "Microsoft WebView2 will be installed if missing. Continue?",
                "Madar Desk Setup", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                return 0;

            string temp = Path.Combine(Path.GetTempPath(), "madar-setup-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temp);
            try {
                using (var zip = ZipFile.OpenRead(Application.ExecutablePath)) {
                    string[] allowed = {
                        "Madar-Desk-v1.0.1-Customer-20261028.exe",
                        "Install-Madar-Customer.ps1", "Madar-Release-Manifest.json",
                        "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
                    };
                    foreach (string name in allowed) {
                        var entry = zip.GetEntry(name);
                        if (entry == null || entry.Length < 100) throw new Exception("Missing or invalid package component: " + name);
                        string target = Path.Combine(temp, name);
                        using (var input = entry.Open())
                        using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write))
                            input.CopyTo(output);
                    }
                }
                if (!qa && !HasWebView2()) {
                    string setup = Path.Combine(temp, "MicrosoftEdgeWebView2RuntimeInstallerX64.exe");
                    int code = RunProcess(setup, "/silent /install", temp);
                    if (code != 0 || !HasWebView2()) throw new Exception("Microsoft WebView2 Runtime installation failed (code " + code + ").");
                }
                string ps = Path.Combine(temp, "Install-Madar-Customer.ps1");
                string argsPs = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(ps) + " -PackageRoot " + Quote(temp);
                if (qa) {
                    argsPs += " -InstallRoot " + Quote(Path.Combine(qaRoot, "Programs", "MadarDesk"));
                    argsPs += " -DataRoot " + Quote(Path.Combine(qaRoot, "Roaming", "MadarDesk"));
                    argsPs += " -BackupRoot " + Quote(Path.Combine(qaRoot, "Backups"));
                }
                int exit = RunProcess(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe"), argsPs, temp);
                if (exit != 0) throw new Exception("Madar installation stopped (code " + exit + "). Your existing data was not deleted.");
                if (qa) {
                    string installed = Path.Combine(qaRoot, "Programs", "MadarDesk", "versions", "1.0.1", "Madar-Desk.exe");
                    if (!File.Exists(installed)) throw new Exception("QA binary was not installed.");
                    Console.WriteLine("QA_INSTALL_PASS: " + installed);
                } else {
                    MessageBox.Show("Madar Desk 1.0.1 is installed. Launch Madar from the Windows Start Menu.",
                        "Madar Desk", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                return 0;
            } finally {
                try { Directory.Delete(temp, true); } catch { /* never delete user data */ }
            }
        } catch (Exception ex) {
            if (qa) Console.Error.WriteLine("QA_INSTALL_FAILED: " + ex.Message);
            else MessageBox.Show(ex.Message, "Madar Setup could not finish", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static string Quote(string str) { return "\"" + str.Replace("\"", "\\\"") + "\""; }
    static int RunProcess(string path, string args, string cwd) {
        using (var proc = new Process()) {
            proc.StartInfo = new ProcessStartInfo(path, args) {
                UseShellExecute = false, CreateNoWindow = true,
                WorkingDirectory = cwd, WindowStyle = ProcessWindowStyle.Hidden
            };
            if (!proc.Start()) throw new Exception("Could not start prerequisite / installer.");
            if (!proc.WaitForExit(180000)) {
                try { proc.Kill(); } catch {}
                throw new Exception("Installation timed out; check the prerequisites.");
            }
            return proc.ExitCode;
        }
    }
    static bool HasWebView2() {
        string subkey = @"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F1D7F7B8-4F5A-4F5F-9A38-9A1E806D2C20}";
        foreach (RegistryKey hive in new [] { Registry.LocalMachine, Registry.CurrentUser }) {
            foreach (RegistryView view in new [] { RegistryView.Registry64, RegistryView.Registry32 }) {
                try {
                    using(var root = RegistryKey.OpenBaseKey(hive == Registry.LocalMachine
                              ? RegistryHive.LocalMachine : RegistryHive.CurrentUser, view))
                    using(var key = root.OpenSubKey(subkey)) {
                        string pv = key == null ? null : key.GetValue("pv") as string;
                        if (!String.IsNullOrWhiteSpace(pv) && pv != "0.0.0.0") return true;
                    }
                } catch { }
            }
        }
        foreach (string root in new [] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                                         Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) }) {
            try {
                string folder = Path.Combine(root, "Microsoft", "EdgeWebView", "Application");
                if (Directory.Exists(folder))
                    foreach (string version in Directory.GetDirectories(folder))
                        if (File.Exists(Path.Combine(version, "msedgewebview2.exe"))) return true;
            } catch {}
        }
        return false;
    }
}
