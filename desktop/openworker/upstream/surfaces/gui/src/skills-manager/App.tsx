import { useState, useEffect, useCallback } from "react";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import { Layout } from "@skills-manager/components/layout/Layout";
import { Skills } from "@skills-manager/pages/Skills";
import { Tools } from "@skills-manager/pages/Tools";
import { Marketplace } from "@skills-manager/pages/Marketplace";
import { Settings } from "@skills-manager/pages/Settings";
import { Feedback } from "@skills-manager/pages/Feedback";
import { EditorPage } from "@skills-manager/pages/Editor";
import { Welcome } from "@skills-manager/pages/Welcome";
import { useInitialization } from "@skills-manager/hooks/useInitialization";
import { ThemeProvider } from "@skills-manager/hooks/useTheme";
import { SkillTranslationProvider } from "@skills-manager/hooks/useSkillTranslation";
import { AuthProvider } from "@skills-manager/contexts/AuthContext";
import { I18nProvider, Language } from "@skills-manager/i18n";
import { FontFamilyPreset, normalizeFontFamilyPreset } from "@skills-manager/lib/fontFamily";
import { AppConfig, MarketplaceUpdateCheckResult } from "@skills-manager/types";
import { ToastContainer, useToast } from "@skills-manager/components/ui/toast";
import { CommandPalette } from "@skills-manager/components/CommandPalette";
import { PageHeaderProvider } from "@skills-manager/components/PageHeaderContext";

type Theme = "light" | "dark" | "system";

function GlobalShortcuts({ onOpenPalette }: { onOpenPalette: () => void }) {
  const navigate = useNavigate();
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (!isMod) return;
      // Cmd+K / Ctrl+K: open command palette
      if (e.key === "k" || e.key === "K") {
        e.preventDefault();
        onOpenPalette();
        return;
      }
      // Cmd+, / Ctrl, (macOS Settings convention): open settings
      if (e.key === ",") {
        e.preventDefault();
        navigate("/settings");
        return;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navigate, onOpenPalette]);
  return null;
}

function App() {
  const { isInitialized, isLoading: initLoading, markInitialized } = useInitialization();
  const [language, setLanguage] = useState<Language>("en");
  const [theme, setTheme] = useState<Theme>("system");
  const [fontFamily, setFontFamily] = useState<FontFamilyPreset>("default");
  const [configLoaded, setConfigLoaded] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { toasts, removeToast } = useToast();

  // Load preferences from config on mount
  useEffect(() => {
    async function loadPreferences() {
      try {
        const config = await invoke<AppConfig>("get_config");
        if (config.preferences?.language) {
          setLanguage(config.preferences.language as Language);
        }
        if (config.preferences?.theme) {
          setTheme(config.preferences.theme as Theme);
        }
        setFontFamily(normalizeFontFamilyPreset(config.preferences?.font_family));
        } catch {
        // Use defaults on error
      }
      setConfigLoaded(true);
    }
    loadPreferences();
  }, []);

  const handleLanguageChange = useCallback((lang: Language) => {
    setLanguage(lang);
  }, []);

  const handleThemeChange = useCallback((newTheme: Theme) => {
    setTheme(newTheme);
  }, []);

  const handleFontFamilyChange = useCallback((newFontFamily: FontFamilyPreset) => {
    setFontFamily(newFontFamily);
  }, []);

  useEffect(() => {
    if (!isInitialized || !configLoaded) {
      return;
    }

    const timer = window.setTimeout(() => {
      void invoke<MarketplaceUpdateCheckResult>("check_marketplace_updates_if_stale").catch(
        () => {
          // keep startup check silent on failures
        },
      );
    }, 20_000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [configLoaded, isInitialized]);


  // Wait for both initialization check and config to load
  if (initLoading || !configLoaded) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!isInitialized) {
    return (
      <ThemeProvider
        theme={theme}
        fontFamily={fontFamily}
        onThemeChange={handleThemeChange}
        onFontFamilyChange={handleFontFamilyChange}
      >
        <I18nProvider language={language} onLanguageChange={handleLanguageChange}>
          <Welcome onComplete={markInitialized} />
        </I18nProvider>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider
      theme={theme}
      fontFamily={fontFamily}
      onThemeChange={handleThemeChange}
      onFontFamilyChange={handleFontFamilyChange}
    >
      <I18nProvider language={language} onLanguageChange={handleLanguageChange}>
        <AuthProvider>
          <MemoryRouter>
            <PageHeaderProvider>
              <SkillTranslationProvider>
                <GlobalShortcuts onOpenPalette={() => setPaletteOpen(true)} />
                <Routes>
                  <Route path="/" element={<Layout onOpenPalette={() => setPaletteOpen(true)} />}>
                    <Route index element={<Skills />} />
                    <Route path="tools" element={<Tools />} />
                    <Route path="marketplace" element={<Marketplace />} />
                    <Route path="settings" element={<Settings />} />
                    <Route path="feedback" element={<Feedback />} />
                  </Route>
                  <Route path="/editor" element={<EditorPage />} />
                </Routes>
                <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
                <ToastContainer toasts={toasts} onRemove={removeToast} />
              </SkillTranslationProvider>
            </PageHeaderProvider>
          </MemoryRouter>
        </AuthProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}

export default App;
