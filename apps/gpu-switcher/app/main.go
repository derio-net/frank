package main

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

//go:embed static
var staticFiles embed.FS

// workloadStatusJSON is the JSON response for a workload status.
type workloadStatusJSON struct {
	Name          string `json:"name"`
	Namespace     string `json:"namespace"`
	Group         string `json:"group"`
	Replicas      int32  `json:"replicas"`
	ReadyReplicas int32  `json:"readyReplicas"`
	PodPhase      string `json:"podPhase"`
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	client, err := buildClient()
	if err != nil {
		log.Fatalf("Failed to create Kubernetes client: %v", err)
	}

	workloads := parseWorkloads()

	mux := http.NewServeMux()

	// Serve static files at root
	staticFS, _ := fs.Sub(staticFiles, "static")
	mux.Handle("/", http.FileServer(http.FS(staticFS)))

	// API: get status of all workloads
	mux.HandleFunc("/api/status", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
		defer cancel()
		statuses, err := GetStatus(ctx, client, workloads)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		resp := make([]workloadStatusJSON, len(statuses))
		for i, s := range statuses {
			resp[i] = workloadStatusJSON{
				Name:          s.Name,
				Namespace:     s.Namespace,
				Group:         groupKey(s.Workload),
				Replicas:      s.Replicas,
				ReadyReplicas: s.ReadyReplicas,
				PodPhase:      s.PodPhase,
			}
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	// API: activate a specific workload
	mux.HandleFunc("/api/activate/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		name := strings.TrimPrefix(r.URL.Path, "/api/activate/")
		if name == "" {
			http.Error(w, "workload name required", http.StatusBadRequest)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		if err := ActivateWorkload(ctx, client, workloads, name); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "activated %s", name)
	})

	// API: deactivate all workloads
	mux.HandleFunc("/api/deactivate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		if err := DeactivateAll(ctx, client, workloads); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "all workloads deactivated")
	})

	log.Printf("GPU Switcher listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

// buildClient creates a Kubernetes clientset using in-cluster config.
func buildClient() (kubernetes.Interface, error) {
	config, err := rest.InClusterConfig()
	if err != nil {
		return nil, fmt.Errorf("in-cluster config: %w", err)
	}
	return kubernetes.NewForConfig(config)
}

// parseWorkloads reads workload definitions from the WORKLOADS env var and
// exits on a malformed value.
// Default: "ollama:ollama:ollama,comfyui:comfyui:comfyui"
func parseWorkloads() []Workload {
	raw := os.Getenv("WORKLOADS")
	if raw == "" {
		raw = "ollama:ollama:ollama,comfyui:comfyui:comfyui"
	}
	workloads, err := ParseWorkloads(raw)
	if err != nil {
		log.Fatal(err)
	}
	return workloads
}

// ParseWorkloads parses "name:namespace:deployment[@group],..." entries.
// Workloads sharing a group are activated together. A group must name a
// workload in the same list; empty entries and duplicate names are rejected.
func ParseWorkloads(raw string) ([]Workload, error) {
	var workloads []Workload
	seen := map[string]bool{}
	for _, entry := range strings.Split(raw, ",") {
		parts := strings.Split(entry, ":")
		if len(parts) != 3 || parts[0] == "" || parts[1] == "" {
			return nil, fmt.Errorf("invalid workload entry: %q (expected name:namespace:deployment[@group])", entry)
		}
		dep, group, hasGroup := strings.Cut(parts[2], "@")
		if dep == "" || (hasGroup && (group == "" || strings.Contains(group, "@"))) {
			return nil, fmt.Errorf("invalid workload entry: %q (expected name:namespace:deployment[@group])", entry)
		}
		if seen[parts[0]] {
			return nil, fmt.Errorf("duplicate workload name: %q", parts[0])
		}
		seen[parts[0]] = true
		workloads = append(workloads, Workload{
			Name:           parts[0],
			Namespace:      parts[1],
			DeploymentName: dep,
			Group:          group,
		})
	}
	for _, w := range workloads {
		if w.Group != "" && !seen[w.Group] {
			return nil, fmt.Errorf("workload %q: group %q names no workload in the list", w.Name, w.Group)
		}
	}
	return workloads, nil
}
