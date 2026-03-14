package main

import (
	"context"
	"testing"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func newTestWorkloads() (*fake.Clientset, []Workload) {
	client := fake.NewSimpleClientset(
		&appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{Name: "ollama", Namespace: "ollama"},
			Spec:       appsv1.DeploymentSpec{Replicas: int32Ptr(1)},
			Status:     appsv1.DeploymentStatus{ReadyReplicas: 1},
		},
		&appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{Name: "comfyui", Namespace: "comfyui"},
			Spec:       appsv1.DeploymentSpec{Replicas: int32Ptr(0)},
			Status:     appsv1.DeploymentStatus{ReadyReplicas: 0},
		},
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name: "ollama-abc123", Namespace: "ollama",
				Labels: map[string]string{"app.kubernetes.io/name": "ollama"},
			},
			Status: corev1.PodStatus{Phase: corev1.PodRunning},
		},
	)
	workloads := []Workload{
		{Name: "ollama", Namespace: "ollama", DeploymentName: "ollama"},
		{Name: "comfyui", Namespace: "comfyui", DeploymentName: "comfyui"},
	}
	return client, workloads
}

func int32Ptr(i int32) *int32 { return &i }

func TestGetStatus(t *testing.T) {
	client, workloads := newTestWorkloads()
	statuses, err := GetStatus(context.Background(), client, workloads)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(statuses) != 2 {
		t.Fatalf("expected 2 statuses, got %d", len(statuses))
	}
	// Ollama should be active (replicas=1)
	if statuses[0].Replicas != 1 {
		t.Errorf("expected ollama replicas=1, got %d", statuses[0].Replicas)
	}
	// ComfyUI should be inactive (replicas=0)
	if statuses[1].Replicas != 0 {
		t.Errorf("expected comfyui replicas=0, got %d", statuses[1].Replicas)
	}
}

func TestActivateWorkload(t *testing.T) {
	client, workloads := newTestWorkloads()
	// Activate comfyui (should scale comfyui to 1, ollama to 0)
	err := ActivateWorkload(context.Background(), client, workloads, "comfyui")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Check comfyui scaled up
	dep, _ := client.AppsV1().Deployments("comfyui").Get(context.Background(), "comfyui", metav1.GetOptions{})
	if *dep.Spec.Replicas != 1 {
		t.Errorf("expected comfyui replicas=1, got %d", *dep.Spec.Replicas)
	}
	// Check ollama scaled down
	dep, _ = client.AppsV1().Deployments("ollama").Get(context.Background(), "ollama", metav1.GetOptions{})
	if *dep.Spec.Replicas != 0 {
		t.Errorf("expected ollama replicas=0, got %d", *dep.Spec.Replicas)
	}
}

func TestActivateWorkload_InvalidName(t *testing.T) {
	client, workloads := newTestWorkloads()
	err := ActivateWorkload(context.Background(), client, workloads, "nonexistent")
	if err == nil {
		t.Fatal("expected error for invalid workload name")
	}
}

func TestDeactivateAll(t *testing.T) {
	client, workloads := newTestWorkloads()
	err := DeactivateAll(context.Background(), client, workloads)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, w := range workloads {
		dep, _ := client.AppsV1().Deployments(w.Namespace).Get(context.Background(), w.DeploymentName, metav1.GetOptions{})
		if *dep.Spec.Replicas != 0 {
			t.Errorf("expected %s replicas=0, got %d", w.Name, *dep.Spec.Replicas)
		}
	}
}
