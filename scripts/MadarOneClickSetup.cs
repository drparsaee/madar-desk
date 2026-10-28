// Single-file GUI installer. The signed-by-nobody Windows .exe holds an
// appended ZIP with a customer package and offline WebView2 prerequisite.
// It never removes user profile data or launches the actual customer app.
using System;
using System.IO;
using System.IO.Compression;
using System.Diagnostics;
using System.Text;
using System.Linq;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class MadarOneClickSetup {
    [STAThread]
    private static int Main(string[] args) {
        Application.EnableVisualStyles();
        bool qa = args.Length == 4 && args[0] == "--qa-isolated";
        string qaRoot = null;
        try {
            // Read-only verification for the actual prerequisite detection
            // used by the customer installer. Does not touch installed data.
            if (args.Length == 1 && args[0] == "--qa-webview-check")
                return HasWebView2() ? 0 : 3;
            if (args.Length != 0 && !qa) throw new Exception("Invalid command line.");
            qaRoot = qa ? Path.GetFullPath(args[1]) : null;
            if (qa && (!Directory.Exists(qaRoot) || !File.Exists(Path.Combine(qaRoot, ".madar-qa-marker"))))
                throw new Exception("Isolated QA folder must exist and be explicitly marked.");
            if (!qa && IsMadarRunning())
                throw new Exception("مدار هنوز باز است. همهٔ پنجره‌های مدار را ببندید و نصب را دوباره اجرا کنید. اطلاعات موجود تغییر نکرده‌اند.");
            if (!qa && MessageBox.Show(
                "مدار نسخه ۱.۰.۱ برای همین کاربر ویندوز نصب می‌شود.\n" +
                "اطلاعات قبلی حفظ می‌شوند و پیش‌نیاز WebView2 در صورت لزوم نصب می‌شود.\n" +
                "نصب را شروع می‌کنید؟",
                "نصب مدار", MessageBoxButtons.YesNo, MessageBoxIcon.Question,
                MessageBoxDefaultButton.Button2,
                MessageBoxOptions.RightAlign | MessageBoxOptions.RtlReading) != DialogResult.Yes)
                return 0;

            bool webviewInstalled = HasWebView2();
            string temp = Path.Combine(Path.GetTempPath(), "madar-setup-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temp);
            try {
                using (var zip = ZipFile.OpenRead(Application.ExecutablePath)) {
                    string[] allowed = {
                        "Madar-Desk-v1.0.1-Customer-20261028.exe",
                        "Install-Madar-Customer.ps1", "Madar-Release-Manifest.json"
                    };
                    // Avoid decompressing 215 MB for an already installed
                    // WebView2 Runtime. No forced reinstall, no privilege prompt.
                    if (!qa && !webviewInstalled)
                        allowed = allowed.Concat(new [] {"MicrosoftEdgeWebView2RuntimeInstallerX64.exe"}).ToArray();
                    foreach (string name in allowed) {
                        var entry = zip.GetEntry(name);
                        if (entry == null || entry.Length < 100) throw new Exception("Missing or invalid package component: " + name);
                        string target = Path.Combine(temp, name);
                        using (var input = entry.Open())
                        using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write))
                            input.CopyTo(output);
                    }
                }
                if (!qa && !webviewInstalled) {
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
                string errorText;
                int exit = RunPowerShell(argsPs, temp, out errorText);
                if (exit != 0) throw new Exception("Madar installation stopped (code " + exit + ").\n" +
                    (errorText.Length == 0 ? "No diagnostic was returned." : errorText) +
                    "\nExisting Madar data has not been removed.");
                if (qa) {
                    string installed = Path.Combine(qaRoot, "Programs", "MadarDesk", "versions", "1.0.1", "Madar-Desk.exe");
                    if (!File.Exists(installed)) throw new Exception("QA binary was not installed.");
                    Console.WriteLine("QA_INSTALL_PASS: " + installed);
                } else {
                    MessageBox.Show("مدار نسخه ۱.۰.۱ نصب شد. برنامه را از منوی Start ویندوز اجرا کنید.",
                        "نصب مدار", MessageBoxButtons.OK, MessageBoxIcon.Information,
                        MessageBoxDefaultButton.Button1,
                        MessageBoxOptions.RightAlign | MessageBoxOptions.RtlReading);
                }
                return 0;
            } finally {
                try { Directory.Delete(temp, true); } catch { /* never delete user data */ }
            }
        } catch (Exception ex) {
            if (qa) {
                Console.Error.WriteLine("QA_INSTALL_FAILED: " + ex.ToString());
                try {
                    if (qaRoot != null && File.Exists(Path.Combine(qaRoot, ".madar-qa-marker")))
                        File.WriteAllText(Path.Combine(qaRoot, "qa-install-result.txt"), ex.ToString());
                } catch {}
            }
            else MessageBox.Show(ex.Message, "خطا در نصب مدار", MessageBoxButtons.OK, MessageBoxIcon.Error,
                MessageBoxDefaultButton.Button1,
                MessageBoxOptions.RightAlign | MessageBoxOptions.RtlReading);
            return 1;
        }
    }

    static string Quote(string str) { return "\"" + str.Replace("\"", "\\\"") + "\""; }
    static bool IsMadarRunning() {
        foreach (Process process in Process.GetProcesses()) {
            using (process) {
                try {
                    if (process.ProcessName.StartsWith("Madar-Desk", StringComparison.OrdinalIgnoreCase) ||
                        process.ProcessName.Equals("MadarHost", StringComparison.OrdinalIgnoreCase))
                        return true;
                } catch {}
            }
        }
        return false;
    }
    static int RunPowerShell(string args, string cwd, out string failure) {
        string program = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                                      "WindowsPowerShell", "v1.0", "powershell.exe");
        using (var process = new Process()) {
            process.StartInfo = new ProcessStartInfo(program, args) {
                UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = cwd,
                WindowStyle = ProcessWindowStyle.Hidden,
                RedirectStandardError = true, RedirectStandardOutput = true
            };
            if (!process.Start()) throw new Exception("Could not start the Windows installation process.");
            var stdOut = process.StandardOutput.ReadToEndAsync();
            var stdErr = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(180000)) {
                try { process.Kill(); } catch {}
                throw new Exception("Installation did not complete within 3 minutes.");
            }
            System.Threading.Tasks.Task.WaitAll(stdOut, stdErr);
            string errors = stdErr.Result.Trim();
            // Windows PowerShell error text includes the precise failing step;
            // cap the user-visible diagnostic instead of a silent generic code.
            failure = errors.Length > 1200 ? errors.Substring(0, 1200) : errors;
            return process.ExitCode;
        }
    }
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
        // Actual Microsoft Edge WebView2 Evergreen Runtime product ID.
        // The previous GUID was wrong and caused needless offline reinstall.
        string subkey = @"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}";
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
