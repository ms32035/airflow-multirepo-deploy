import { Box, Button, HStack, Input, Text, VStack, Spinner } from "@chakra-ui/react";
import { useEffect, useState } from "react";

interface AddRepoModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const AddRepoModal = ({ isOpen, onClose, onSuccess }: AddRepoModalProps) => {
  const [method, setMethod] = useState<"ssh" | "github">("ssh");
  const [githubAvailable, setGithubAvailable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // SSH form state
  const [repoUrl, setRepoUrl] = useState("");
  const [folderName, setFolderName] = useState("");
  const [sshKeyFile, setSshKeyFile] = useState<File | null>(null);

  // GitHub form state
  const [githubRepos, setGithubRepos] = useState<Array<{ name: string; full_name: string; description: string }>>([]);
  const [selectedGithubRepo, setSelectedGithubRepo] = useState("");
  const [loadingRepos, setLoadingRepos] = useState(false);

  useEffect(() => {
    const checkGithubAvailability = async () => {
      if (!isOpen) return;

      try {
        const response = await fetch("/deployment/api/repos/github-available");
        const data = await response.json();
        setGithubAvailable(data.available);
        if (!data.available) {
          setMethod("ssh");
        }
      } catch (err) {
        console.error("Failed to check GitHub availability:", err);
      }
    };

    checkGithubAvailability();
  }, [isOpen]);

  useEffect(() => {
    const fetchGithubRepos = async () => {
      if (method === "github" && githubAvailable && isOpen) {
        setLoadingRepos(true);
        setError(null);
        try {
          const response = await fetch("/deployment/api/repos/github-list");
          const data = await response.json();
          if (response.ok) {
            setGithubRepos(data.repos || []);
          } else {
            setError(data.error || "Failed to fetch GitHub repositories");
          }
        } catch (err) {
          setError("Failed to fetch GitHub repositories");
        } finally {
          setLoadingRepos(false);
        }
      } else if (method === "ssh") {
        // Clear GitHub repos when switching to SSH
        setGithubRepos([]);
        setSelectedGithubRepo("");
      }
    };

    fetchGithubRepos();
  }, [method, githubAvailable, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validate before setting loading state
    if (method === "ssh") {
      if (!repoUrl || !folderName || !sshKeyFile) {
        setError("Please fill in all fields and select an SSH key file");
        return;
      }
    } else if (method === "github") {
      if (!selectedGithubRepo || !folderName) {
        setError("Please select a repository and enter a folder name");
        return;
      }
    }

    setLoading(true);

    try {
      if (method === "ssh") {
        const formData = new FormData();
        formData.append("repo_url", repoUrl);
        formData.append("folder_name", folderName);
        formData.append("ssh_key", sshKeyFile!);

        const response = await fetch("/deployment/api/repos/add-ssh", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || "Failed to add repository");
        }

        const result = await response.json();
        setSuccess(result.success || "Repository added successfully!");
        setTimeout(() => {
          onSuccess();
          onClose();
        }, 1500);
      } else {
        // GitHub method
        const formData = new FormData();
        formData.append("repo_full_name", selectedGithubRepo);
        formData.append("folder_name", folderName);

        const response = await fetch("/deployment/api/repos/add-github", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || "Failed to add repository");
        }

        const result = await response.json();
        setSuccess(result.success || "Repository added successfully!");
        setTimeout(() => {
          onSuccess();
          onClose();
        }, 1500);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setRepoUrl("");
    setMethod("ssh");
    setLoading(false);
    setLoadingRepos(false);
    setFolderName("");
    setSshKeyFile(null);
    setSelectedGithubRepo("");
    setGithubRepos([]);
    setError(null);
    setSuccess(null);
    onClose();
  };

  const handleGithubRepoSelect = (fullName: string) => {
    setSelectedGithubRepo(fullName);
    // Auto-populate folder name from repo name
    const repoName = fullName.split("/")[1];
    if (!folderName) {
      setFolderName(repoName);
    }
  };

  if (!isOpen) return null;

  return (
    <Box
      position="fixed"
      top={0}
      left={0}
      right={0}
      bottom={0}
      bg="rgba(0, 0, 0, 0.5)"
      display="flex"
      alignItems="center"
      justifyContent="center"
      zIndex={1000}
      onClick={handleClose}
    >
      <Box
        bg="bg"
        borderRadius="lg"
        border="1px"
        borderColor="border"
        p={6}
        maxW="600px"
        w="90%"
        onClick={(e) => e.stopPropagation()}
      >
        <VStack gap={4} align="stretch">
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Text fontSize="2xl" fontWeight="bold">
              Add Repository
            </Text>
            <Button size="sm" variant="ghost" onClick={handleClose}>
              ✕
            </Button>
          </Box>

          {/* Method selection tabs */}
          <HStack gap={2}>
            <Button
              size="sm"
              colorPalette={method === "ssh" ? "brand" : undefined}
              variant={method === "ssh" ? "solid" : "outline"}
              onClick={() => setMethod("ssh")}
            >
              SSH Key
            </Button>
            <Button
              size="sm"
              colorPalette={method === "github" ? "brand" : undefined}
              variant={method === "github" ? "solid" : "outline"}
              onClick={() => setMethod("github")}
              disabled={!githubAvailable}
            >
              GitHub App {!githubAvailable && "(Not configured)"}
            </Button>
          </HStack>

          {success && (
            <Box p={3} bg="green.50" color="green.800" borderRadius="md" border="1px" borderColor="green.200">
              <Text>{success}</Text>
            </Box>
          )}

          {error && (
            <Box p={3} bg="red.50" color="red.800" borderRadius="md" border="1px" borderColor="red.200">
              <Text>{error}</Text>
            </Box>
          )}

          <form onSubmit={handleSubmit}>
            <VStack gap={4} align="stretch">
              {method === "ssh" && (
                <>
                  <Box>
                    <Text mb={2} fontWeight="semibold">
                      Repository URL (SSH)
                    </Text>
                    <Input
                      placeholder="git@github.com:username/repo.git"
                      value={repoUrl}
                      onChange={(e) => setRepoUrl(e.target.value)}
                      disabled={loading}
                    />
                  </Box>

                  <Box>
                    <Text mb={2} fontWeight="semibold">
                      Folder Name
                    </Text>
                    <Input
                      placeholder="my-repo"
                      value={folderName}
                      onChange={(e) => setFolderName(e.target.value)}
                      disabled={loading}
                    />
                  </Box>

                  <Box>
                    <Text mb={2} fontWeight="semibold">
                      SSH Private Key
                    </Text>
                    <Input
                      type="file"
                      accept=".pem,.key,*"
                      onChange={(e) => setSshKeyFile(e.target.files?.[0] || null)}
                      disabled={loading}
                      p={1}
                    />
                  </Box>
                </>
              )}

              {method === "github" && (
                <>
                  {loadingRepos ? (
                    <Box display="flex" alignItems="center" justifyContent="center" p={4}>
                      <Spinner size="sm" mr={2} />
                      <Text>Loading repositories...</Text>
                    </Box>
                  ) : githubRepos.length === 0 ? (
                    <Box p={4} bg="yellow.50" color="yellow.800" borderRadius="md">
                      <Text fontSize="sm">
                        No repositories available. Make sure the GitHub App has access to repositories in your organization.
                      </Text>
                    </Box>
                  ) : (
                    <>
                      <Box>
                        <Text mb={2} fontWeight="semibold">
                          Select Repository
                        </Text>
                        <select
                          value={selectedGithubRepo}
                          onChange={(e) => handleGithubRepoSelect(e.target.value)}
                          disabled={loading}
                          style={{
                            width: "100%",
                            padding: "8px",
                            borderRadius: "6px",
                            border: "1px solid var(--chakra-colors-border)",
                            backgroundColor: "var(--chakra-colors-bg)",
                            color: "var(--chakra-colors-fg)",
                          }}
                        >
                          <option value="">Select a repository...</option>
                          {githubRepos.map((repo) => (
                            <option key={repo.full_name} value={repo.full_name}>
                              {repo.full_name} {repo.description && `- ${repo.description}`}
                            </option>
                          ))}
                        </select>
                      </Box>

                      <Box>
                        <Text mb={2} fontWeight="semibold">
                          Folder Name
                        </Text>
                        <Input
                          placeholder="my-repo"
                          value={folderName}
                          onChange={(e) => setFolderName(e.target.value)}
                          disabled={loading}
                        />
                      </Box>
                    </>
                  )}
                </>
              )}

              <HStack gap={3} justify="flex-end" mt={4}>
                <Button variant="outline" onClick={handleClose} disabled={loading}>
                  Cancel
                </Button>
                <Button type="submit" colorPalette="brand" disabled={loading}>
                  {loading ? (
                    <HStack gap={2}>
                      <Spinner size="sm" />
                      <Text>Adding...</Text>
                    </HStack>
                  ) : (
                    "Add Repository"
                  )}
                </Button>
              </HStack>
            </VStack>
          </form>
        </VStack>
      </Box>
    </Box>
  );
};
