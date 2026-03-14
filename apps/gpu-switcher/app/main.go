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

// parseWorkloads reads workload definitions from the WORKLOADS env var.
// Format: "name:namespace:deployment,name:namespace:deployment,..."
// Default: "ollama:ollama:ollama,comfyui:comfyui:comfyui"
func parseWorkloads() []Workload {
	raw := os.Getenv("WORKLOADS")
	if raw == "" {
		raw = "ollama:ollama:ollama,comfyui:comfyui:comfyui"
	}
	var workloads []Workload
	for _, entry := range strings.Split(raw, ",") {
		parts := strings.SplitN(entry, ":", 3)
		if len(parts) != 3 {
			log.Fatalf("invalid workload entry: %s (expected name:namespace:deployment)", entry)
		}
		workloads = append(workloads, Workload{
			Name:           parts[0],
			Namespace:      parts[1],
			DeploymentName: parts[2],
		})
	}
	return workloads
}
