// React imports
// UI Component imports
import { Box, Button, Code, Heading, HStack, Spinner, Text, VStack } from "@chakra-ui/react";
import { useEffect, useState } from "react";

// Context imports
import { useColorMode } from "src/context/colorMode";

/**
 * Repository information from the API
 */
interface Repository {
  folder: string;
  active_branch: string | null;
  committed_date_str: string | null;
  sha: string | null;
  author: string | null;
  commit_message: string | null;
  remotes: [string, string][]; // [name, url] pairs
  local_branches: string[];
  remote_branches: string[];
}

/**
 * Form data for deployment options
 */
interface DeployForm {
  branches: string[];
  selected: string;
}

/**
 * Complete data structure returned by the status API
 */
interface DeployPageData {
  repo: Repository;
  form: DeployForm;
  errors?: string[] | null;
}

/**
 * Response from the deployment API
 */
interface DeployResponse {
  success?: string;
  errors?: string[];
}

export const Deploy = () => {
  const { colorMode, setColorMode } = useColorMode();
  const [data, setData] = useState<DeployPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deployResponse, setDeployResponse] = useState<DeployResponse | null>(null);
  const [selectedBranch, setSelectedBranch] = useState<string>("");
  const [deploying, setDeploying] = useState(false);
  const [cleanupResponse, setCleanupResponse] = useState<{ success?: boolean; message?: string; error?: string } | null>(null);
  const [cleaningUp, setCleaningUp] = useState(false);

  // Get folder from URL hash
  const folder = window.location.hash.match(/#\/status\/(.+)$/)?.[1] || "";

  const handleBackToRepos = () => {
    // Use hash navigation to return to repo list
    window.location.hash = "";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };

  useEffect(() => {
    const fetchDeployData = async () => {
      // Don't try to fetch if we don't have a folder name
      if (!folder) {
        setLoading(false);
        setError("No repository specified");
        return;
      }
      try {
        const response = await fetch(`/deployment/api/status/${folder}`, {
          headers: {
            Accept: "application/json",
          },
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const deployData: DeployPageData = await response.json();
        setData(deployData);
        const initialBranch = deployData.form.branches.includes(deployData.form.selected)
          ? deployData.form.selected
          : (deployData.form.branches[0] ?? "");
        setSelectedBranch(initialBranch);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred while fetching repository data");
      } finally {
        setLoading(false);
      }
    };

    fetchDeployData();
  }, [folder]);

  const handleDeploy = async () => {
    if (!folder || !selectedBranch || !data) return;

    setDeploying(true);
    setDeployResponse(null);

    try {
      const formData = new FormData();
      formData.append("branches", selectedBranch);

      const response = await fetch(`/deployment/deploy/${folder}`, {
        body: formData,
        headers: {
          Accept: "application/json",
        },
        method: "POST",
      });

      if (response.ok) {
        const result = await response.json();
        setDeployResponse({ success: result.success || "Deployment successful!" });
      } else {
        const result = await response.json();
        // Handle both string errors and array-of-strings error format
        const errorData = result.error || "Deployment failed";
        setDeployResponse({
          errors: Array.isArray(errorData) ? [errorData.join("")] : [errorData],
        });
      }
    } catch (err) {
      setDeployResponse({
        errors: [err instanceof Error ? err.message : "An error occurred during deployment"],
      });
    } finally {
      setDeploying(false);
    }
  };

  const handleCleanupBranches = async () => {
    if (!folder) return;

    setCleaningUp(true);
    setCleanupResponse(null);

    try {
      const response = await fetch(`/deployment/api/cleanup-branches/${folder}`, {
        method: "POST",
        headers: {
          Accept: "application/json",
        },
      });

      if (response.ok) {
        const result = await response.json();
        const deletedCount = result.deleted_branches?.length || 0;
        setCleanupResponse({
          success: true,
          message: `Successfully deleted ${deletedCount} branch${deletedCount !== 1 ? "es" : ""}. Active branch: ${result.active_branch}`,
        });
        // Refresh the page data to show updated branch list
        setTimeout(() => {
          window.location.reload();
        }, 2000);
      } else {
        const result = await response.json();
        setCleanupResponse({
          error: result.error || "Failed to cleanup branches",
        });
      }
    } catch (err) {
      setCleanupResponse({
        error: err instanceof Error ? err.message : "An error occurred during branch cleanup",
      });
    } finally {
      setCleaningUp(false);
    }
  };

  if (loading) {
    return (
      <Box p={8} bg="bg.subtle" flexGrow={1} height="100%">
        <VStack gap={8} align="center" justify="center" flexGrow={1} height="100%">
          <Spinner size="xl" color="brand.500" />
          <Text fontSize="lg" color="fg.muted">
            Loading repository details...
          </Text>
        </VStack>
      </Box>
    );
  }

  if (error || !data) {
    return (
      <Box p={8} bg="bg.subtle" flexGrow={1} height="100%">
        <VStack gap={8} align="center" justify="center" flexGrow={1} height="100%">
          <Box p={4} bg="red.50" color="red.800" borderRadius="md" border="1px" borderColor="red.200">
            <Text fontWeight="bold">Error loading repository!</Text>
            <Text>{error || "Repository data not found"}</Text>
          </Box>
          <Button onClick={() => window.location.reload()} colorPalette="brand">
            Retry
          </Button>
        </VStack>
      </Box>
    );
  }

  const { form, repo } = data;

  return (
    <Box p={6} bg="bg.subtle" minHeight="100vh">
      <VStack gap={6} align="stretch" maxW="6xl" mx="auto">
        {/* Header with navigation */}
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <HStack gap={4} align="center">
            <Button size="sm" variant="outline" onClick={handleBackToRepos}>
              ← Back to Repositories
            </Button>
            <Heading size="xl" color="fg">
              {repo.folder}
            </Heading>


        {/* Cleanup Messages */}
        {cleanupResponse?.success && cleanupResponse?.message && (
          <Box p={4} bg="green.50" color="green.800" borderRadius="md" border="1px" borderColor="green.200">
            <Text>{cleanupResponse.message}</Text>
          </Box>
        )}

        {cleanupResponse?.error && (
          <Box p={4} bg="red.50" color="red.800" borderRadius="md" border="1px" borderColor="red.200">
            <Text fontWeight="bold">Branch cleanup failed:</Text>
            <Text fontSize="sm" mt={1}>{cleanupResponse.error}</Text>
          </Box>
        )}</HStack>
          <Button
            onClick={() => setColorMode(colorMode === "dark" ? "light" : "dark")}
            size="sm"
            variant="outline"
          >
            Toggle Theme
          </Button>
        </Box>

        {/* Success/Error Messages */}
        {deployResponse?.success && (
          <Box p={4} bg="green.50" color="green.800" borderRadius="md" border="1px" borderColor="green.200">
            <Text>{deployResponse.success}</Text>
          </Box>
        )}

        {deployResponse?.errors && (
          <Box p={4} bg="red.50" color="red.800" borderRadius="md" border="1px" borderColor="red.200">
            <Text fontWeight="bold" mb={2}>
              Errors occurred:
            </Text>
            <VStack align="stretch" gap={2}>
              {deployResponse.errors.map((error, index) => (
                <Box
                  key={index}
                  as="pre"
                  fontSize="sm"
                  fontFamily="mono"
                  whiteSpace="pre-wrap"
                  p={2}
                  bg="red.100"
                  borderRadius="sm"
                  overflowX="auto"
                >
                  {error}
                </Box>
              ))}
            </VStack>
          </Box>
        )}

        {/* Cleanup Messages */}
        {cleanupResponse?.success && cleanupResponse?.message && (
          <Box p={4} bg="green.50" color="green.800" borderRadius="md" border="1px" borderColor="green.200">
            <Text>{cleanupResponse.message}</Text>
          </Box>
        )}

        {cleanupResponse?.error && (
          <Box p={4} bg="red.50" color="red.800" borderRadius="md" border="1px" borderColor="red.200">
            <Text fontWeight="bold">Branch cleanup failed:</Text>
            <Text fontSize="sm" mt={1}>{cleanupResponse.error}</Text>
          </Box>
        )}

        {/* Display Git fetch errors */}
        {data?.errors &&
          Array.isArray(data.errors) &&
          data.errors.some((error) => Boolean(error?.trim())) && (
            <Box p={4} bg="red.50" color="red.800" borderRadius="md" border="1px" borderColor="red.200">
              <Text fontWeight="bold">Error - Remote fetch issues:</Text>
              <Text fontSize="sm" mb={2}>
                These Git errors indicate problems connecting to the remote repository. Deployment may still
                be possible with local branches.
              </Text>
              <VStack align="stretch" gap={2}>
                {data.errors.filter(Boolean).map((error, index) => (
                  <Box
                    key={index}
                    as="pre"
                    fontSize="xs"
                    fontFamily="mono"
                    whiteSpace="pre-wrap"
                    p={2}
                    bg="red.100"
                    borderRadius="sm"
                  >
                    {error}
                  </Box>
                ))}
              </VStack>
            </Box>
          )}

        {/* Repository Details */}
        <Box bg="bg" borderRadius="lg" border="1px" borderColor="border" overflow="hidden">
          <Box p={4}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={4}>
              <Heading size="md">Repository Details</Heading>
              <Button
                size="sm"
                colorPalette="red"
                variant="outline"
                onClick={handleCleanupBranches}
                disabled={cleaningUp || !data?.repo?.local_branches || data.repo.local_branches.length <= 1}
              >
                {cleaningUp ? "Cleaning up..." : "Cleanup Branches"}
              </Button>
            </Box>
            <Box as="table" w="full" borderCollapse="collapse">
              <Box as="tbody">
                {/* Repository information table rows */}
                <Box as="tr">
                  <Box as="th" py={2} pr={4} textAlign="left" fontWeight="semibold" color="fg" width="150px">
                    Git hash
                  </Box>
                  <Box as="td" py={2}>
                    <Code fontSize="sm">{repo.sha}</Code>
                  </Box>
                </Box>
                <Box as="tr">
                  <Box as="th" py={2} pr={4} textAlign="left" fontWeight="semibold" color="fg">
                    Commit message
                  </Box>
                  <Box as="td" py={2}>
                    <Box as="pre" fontSize="sm" fontFamily="mono" whiteSpace="pre-wrap" color="fg">
                      {repo.commit_message}
                    </Box>
                  </Box>
                </Box>
                <Box as="tr">
                  <Box as="th" py={2} pr={4} textAlign="left" fontWeight="semibold" color="fg">
                    Author
                  </Box>
                  <Box as="td" py={2}>
                    {repo.author}
                  </Box>
                </Box>
                <Box as="tr">
                  <Box as="th" py={2} pr={4} textAlign="left" fontWeight="semibold" color="fg">
                    Committed
                  </Box>
                  <Box as="td" py={2}>
                    {repo.committed_date_str}
                  </Box>
                </Box>
                <Box as="tr">
                  <Box as="th" py={2} pr={4} textAlign="left" fontWeight="semibold" color="fg">
                    Active branch
                  </Box>
                  <Box as="td" py={2}>
                    {repo.active_branch}
                  </Box>
                </Box>
                <Box as="tr">
                  <Box as="th" py={2} pr={4} textAlign="left" fontWeight="semibold" color="fg">
                    Local branches
                  </Box>
                  <Box as="td" py={2}>
                    <HStack wrap="wrap" gap={2}>
                      {repo.local_branches.map((branch) => (
                        <Box
                          key={branch}
                          px={2}
                          py={1}
                          bg="gray.100"
                          color="gray.800"
                          borderRadius="sm"
                          fontSize="xs"
                        >
                          {branch}
                        </Box>
                      ))}
                    </HStack>
                  </Box>
                </Box>
                <Box as="tr">
                  <Box as="th" py={2} pr={4} textAlign="left" fontWeight="semibold" color="fg">
                    Remotes
                  </Box>
                  <Box as="td" py={2}>
                    <VStack align="start" gap={1}>
                      {repo.remotes.map(([name, url], index) => (
                        <Box key={index}>
                          <Box
                            as="span"
                            px={2}
                            py={1}
                            bg="blue.100"
                            color="blue.800"
                            borderRadius="sm"
                            fontSize="xs"
                            mr={2}
                          >
                            {name}
                          </Box>
                          <Text as="span" fontSize="sm" color="fg.muted">
                            {url}
                          </Text>
                        </Box>
                      ))}
                    </VStack>
                  </Box>
                </Box>
              </Box>
            </Box>
          </Box>
        </Box>

        {/* Deploy Form */}
        <Box bg="bg" borderRadius="lg" border="1px" borderColor="border" p={4}>
          <Heading size="md" mb={4}>
            Deploy branch
          </Heading>
          <HStack gap={4} align="center">
            <Text fontWeight="semibold" minW="fit-content">
              Git branches:
            </Text>
            <select
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
              style={{
                backgroundColor: "var(--chakra-colors-bg)",
                border: "1px solid var(--chakra-colors-border)",
                borderRadius: "6px",
                color: "var(--chakra-colors-fg)",
                maxWidth: "300px",
                padding: "8px",
              }}
            >
              {form.branches.map((branch) => (
                <option key={branch} value={branch}>
                  {branch}
                </option>
              ))}
            </select>
            <Button colorScheme="green" onClick={handleDeploy} disabled={!selectedBranch || deploying}>
              {deploying ? "Deploying..." : "Deploy"}
            </Button>
          </HStack>
        </Box>
      </VStack>
    </Box>
  );
};
