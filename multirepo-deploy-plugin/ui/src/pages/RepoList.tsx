import { Box, Button, Heading, Text, VStack, Spinner, Code } from "@chakra-ui/react";
import { useEffect, useState } from "react";

import { useColorMode } from "src/context/colorMode";

// Simple search icon using Unicode
const SearchIcon = () => (
  <Text fontSize="sm" fontWeight="bold">
    🔍
  </Text>
);

interface Repository {
  folder: string;
  active_branch: string | null;
  committed_date_str: string | null;
  sha: string | null;
  author: string | null;
  commit_message: string | null;
  remotes: [string, string][];
  local_branches: string[];
  remote_branches: string[];
}

interface ReposResponse {
  repos: Repository[];
}

export const RepoList = () => {
  const { colorMode, setColorMode } = useColorMode();
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRepos = async () => {
      try {
        const response = await fetch("/deployment/api/repos");
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data: ReposResponse = await response.json();
        setRepos(data.repos);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred while fetching repositories");
      } finally {
        setLoading(false);
      }
    };

    fetchRepos();
  }, []);

  const handleRepoDetails = (folder: string) => {
    // Use hash navigation so the hosting server always serves the same index page
    // and the client-side app handles the route.
    window.location.hash = `/status/${folder}`;
    // Notify listeners
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };

  if (loading) {
    return (
      <Box p={8} bg="bg.subtle" flexGrow={1} height="100%">
        <VStack gap={8} align="center" justify="center" flexGrow={1} height="100%">
          <Spinner size="xl" color="brand.500" />
          <Text fontSize="lg" color="fg.muted">
            Loading repositories...
          </Text>
        </VStack>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={8} bg="bg.subtle" flexGrow={1} height="100%">
        <VStack gap={8} align="center" justify="center" flexGrow={1} height="100%">
          <Box p={4} bg="red.50" color="red.800" borderRadius="md" border="1px" borderColor="red.200">
            <Text>Error loading repositories: {error}</Text>
          </Box>
          <Button onClick={() => window.location.reload()} colorPalette="brand">
            Retry
          </Button>
        </VStack>
      </Box>
    );
  }

  return (
    <Box p={6} bg="bg.subtle" height="100vh" display="flex" flexDirection="column">
      <VStack gap={6} align="stretch" height="100%" overflow="hidden">
        <Box display="flex" justifyContent="space-between" alignItems="center" flexShrink={0}>
          <Heading size="xl" color="fg">
            Repositories
          </Heading>
          <Button
            onClick={() => setColorMode(colorMode === "dark" ? "light" : "dark")}
            size="sm"
            variant="outline"
          >
            Toggle Theme
          </Button>
        </Box>

        {repos.length === 0 ? (
          <VStack gap={4} align="center" justify="center" flexGrow={1}>
            <Text fontSize="lg" color="fg.muted">
              No repositories found
            </Text>
          </VStack>
        ) : (
          <Box
            bg="bg"
            borderRadius="lg"
            border="1px"
            borderColor="border"
            overflow="hidden"
            maxHeight="calc(100vh - 200px)"
            display="flex"
            flexDirection="column"
          >
            <Box overflowY="auto" flexGrow={1}>
              <Box as="table" w="full" borderCollapse="collapse">
                <Box as="thead" bg="bg.muted" position="sticky" top={0} zIndex={1}>
                  <Box as="tr">
                    <Box
                      as="th"
                      p={4}
                      textAlign="left"
                      fontWeight="semibold"
                      color="fg"
                      borderBottom="1px"
                      borderColor="border"
                    >
                      Folder
                    </Box>
                    <Box
                      as="th"
                      p={4}
                      textAlign="left"
                      fontWeight="semibold"
                      color="fg"
                      borderBottom="1px"
                      borderColor="border"
                    >
                      Branch
                    </Box>
                    <Box
                      as="th"
                      p={4}
                      textAlign="left"
                      fontWeight="semibold"
                      color="fg"
                      borderBottom="1px"
                      borderColor="border"
                    >
                      Committed
                    </Box>
                    <Box
                      as="th"
                      p={4}
                      textAlign="left"
                      fontWeight="semibold"
                      color="fg"
                      borderBottom="1px"
                      borderColor="border"
                    >
                      Git Hash
                    </Box>
                    <Box
                      as="th"
                      p={4}
                      textAlign="left"
                      fontWeight="semibold"
                      color="fg"
                      borderBottom="1px"
                      borderColor="border"
                    >
                      Author
                    </Box>
                  </Box>
                </Box>
                <Box as="tbody">
                  {repos.map((repo) => (
                    <Box
                      key={repo.folder}
                      as="tr"
                      _hover={{ bg: "bg.muted" }}
                      borderBottom="1px"
                      borderColor="border.subtle"
                    >
                      <Box as="td" p={4}>
                        <Box display="flex" alignItems="center" gap={2}>
                          <Button
                            size="sm"
                            variant="outline"
                            colorPalette="brand"
                            onClick={() => handleRepoDetails(repo.folder)}
                            px={2}
                            minW="auto"
                          >
                            <SearchIcon />
                          </Button>
                          <Text>{repo.folder}</Text>
                        </Box>
                      </Box>
                      <Box as="td" p={4}>
                        <Text>{repo.active_branch || "-"}</Text>
                      </Box>
                      <Box as="td" p={4}>
                        <Text>{repo.committed_date_str || "-"}</Text>
                      </Box>
                      <Box as="td" p={4}>
                        {repo.sha ? <Code fontSize="sm">{repo.sha.substring(0, 8)}</Code> : <Text>-</Text>}
                      </Box>
                      <Box as="td" p={4}>
                        <Text>{repo.author || "-"}</Text>
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Box>
            </Box>
          </Box>
        )}
      </VStack>
    </Box>
  );
};
