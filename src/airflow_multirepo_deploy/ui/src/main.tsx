import { ChakraProvider } from "@chakra-ui/react";
import { FC, useEffect, useState } from "react";

import { ColorModeProvider } from "src/context/colorMode";
import { Deploy } from "src/pages/Deploy.tsx";
import { RepoList } from "src/pages/RepoList.tsx";

import { system } from "./theme";

export interface PluginComponentProps {
  // Add any props your plugin component needs
}

/**
 * Simple router to handle different views based on URL path
 */
const Router: FC = () => {
  const [currentView, setCurrentView] = useState<"repos" | "deploy">("repos");

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash || "";
      const statusMatch = hash.match(/#\/status\/(.+)$/);

      if (statusMatch && statusMatch[1]) {
        setCurrentView("deploy");
      } else {
        setCurrentView("repos");
      }
    };

    // Initial check
    handleHashChange();

    // Listen for hash changes
    window.addEventListener("hashchange", handleHashChange);

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  if (currentView === "deploy") {
    return <Deploy />;
  }

  return <RepoList />;
};

/**
 * Main plugin component
 */
const PluginComponent: FC<PluginComponentProps> = () => {
  return (
    <ChakraProvider value={system}>
      <ColorModeProvider>
        <Router />
      </ColorModeProvider>
    </ChakraProvider>
  );
};

export default PluginComponent;
