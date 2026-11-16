package main

import (
	"context"
	"os"
	"strings"
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

func newGroupWorkloads() (*fake.Clientset, []Workload) {
	mk := func(name string, r int32) *appsv1.Deployment {
		return &appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: name},
			Spec:       appsv1.DeploymentSpec{Replicas: int32Ptr(r)},
		}
	}
	client := fake.NewSimpleClientset(mk("ollama", 0), mk("speech", 0), mk("comfyui", 1))
	return client, []Workload{
		{Name: "ollama", Namespace: "ollama", DeploymentName: "ollama"},
		{Name: "speech", Namespace: "speech", DeploymentName: "speech", Group: "ollama"},
		{Name: "comfyui", Namespace: "comfyui", DeploymentName: "comfyui"},
	}
}

func replicasOf(t *testing.T, c *fake.Clientset, name string) int32 {
	t.Helper()
	dep, err := c.AppsV1().Deployments(name).Get(context.Background(), name, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("get %s: %v", name, err)
	}
	return *dep.Spec.Replicas
}

func TestActivateGroupFromMember(t *testing.T) {
	client, workloads := newGroupWorkloads()
	if err := ActivateWorkload(context.Background(), client, workloads, "speech"); err != nil {
		t.Fatal(err)
	}
	if replicasOf(t, client, "ollama") != 1 || replicasOf(t, client, "speech") != 1 || replicasOf(t, client, "comfyui") != 0 {
		t.Errorf("speech activation should scale ollama+speech=1, comfyui=0")
	}
}

func TestActivateGroupFromLeader(t *testing.T) {
	client, workloads := newGroupWorkloads()
	if err := ActivateWorkload(context.Background(), client, workloads, "ollama"); err != nil {
		t.Fatal(err)
	}
	if replicasOf(t, client, "speech") != 1 || replicasOf(t, client, "comfyui") != 0 {
		t.Errorf("ollama activation should also scale speech=1, comfyui=0")
	}
}

func TestActivateComfyUIScalesGroupDown(t *testing.T) {
	client, workloads := newGroupWorkloads()
	_ = ActivateWorkload(context.Background(), client, workloads, "speech")
	if err := ActivateWorkload(context.Background(), client, workloads, "comfyui"); err != nil {
		t.Fatal(err)
	}
	if replicasOf(t, client, "ollama") != 0 || replicasOf(t, client, "speech") != 0 || replicasOf(t, client, "comfyui") != 1 {
		t.Errorf("comfyui activation should scale ollama and speech to 0")
	}
}

func TestDeactivateAllWithGroups(t *testing.T) {
	client, workloads := newGroupWorkloads()
	_ = ActivateWorkload(context.Background(), client, workloads, "speech")
	if err := DeactivateAll(context.Background(), client, workloads); err != nil {
		t.Fatal(err)
	}
	for _, n := range []string{"ollama", "speech", "comfyui"} {
		if replicasOf(t, client, n) != 0 {
			t.Errorf("%s should be 0", n)
		}
	}
}

func TestParseWorkloadsGrammar(t *testing.T) {
	ws, err := ParseWorkloads("ollama:ollama:ollama,speech:speech:speech@ollama")
	if err != nil {
		t.Fatal(err)
	}
	if len(ws) != 2 || ws[0].Group != "" || ws[1].Group != "ollama" || ws[1].DeploymentName != "speech" {
		t.Errorf("unexpected parse: %+v", ws)
	}
	for _, bad := range []string{"a:b", "a:b:c@", "a:b:@g", "a:b:c:d", ":b:c", "a:b:c@g@h",
		"ollama:ollama:ollama,speech:speech:speech@olama", // group names no workload
		"ollama:ollama:ollama,",                            // trailing comma / empty entry
		"",                                                 // empty list
		"a:b:c,a:b:d",                                      // duplicate name
	} {
		if _, err := ParseWorkloads(bad); err == nil {
			t.Errorf("expected error for %q", bad)
		}
	}
}

// The real gpu-switcher Deployment's WORKLOADS value must parse and place
// speech in the ollama group (this is the contract the manifest ships).
func TestShippedWorkloadsValueParses(t *testing.T) {
	data, err := os.ReadFile("../manifests/deployment.yaml")
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(string(data), "\n")
	val := ""
	for i, l := range lines {
		if strings.Contains(l, "name: WORKLOADS") && i+1 < len(lines) {
			v := strings.TrimSpace(lines[i+1])
			v = strings.TrimPrefix(v, "value:")
			val = strings.Trim(strings.TrimSpace(v), "\"")
		}
	}
	if val == "" {
		t.Fatal("WORKLOADS value not found in deployment.yaml")
	}
	ws, err := ParseWorkloads(val)
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, w := range ws {
		if w.Name == "speech" {
			found = true
			if w.Namespace != "speech" || w.DeploymentName != "speech" || w.Group != "ollama" {
				t.Errorf("unexpected speech workload: %+v", w)
			}
		}
	}
	if !found {
		t.Error("speech workload missing from shipped WORKLOADS")
	}
}
