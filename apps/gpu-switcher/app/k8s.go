package main

import (
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

// Workload represents a GPU workload that can be activated/deactivated.
type Workload struct {
	Name           string // Display name (e.g., "ollama", "comfyui")
	Namespace      string // Kubernetes namespace
	DeploymentName string // Deployment to scale
}

// WorkloadStatus is the current state of a workload.
type WorkloadStatus struct {
	Workload
	Replicas      int32  // Desired replicas
	ReadyReplicas int32  // Running and ready
	PodPhase      string // Phase of first matching pod, or "None"
}

// GetStatus returns the current status of all workloads.
func GetStatus(ctx context.Context, client kubernetes.Interface, workloads []Workload) ([]WorkloadStatus, error) {
	statuses := make([]WorkloadStatus, 0, len(workloads))
	for _, w := range workloads {
		dep, err := client.AppsV1().Deployments(w.Namespace).Get(ctx, w.DeploymentName, metav1.GetOptions{})
		if err != nil {
			return nil, fmt.Errorf("get deployment %s/%s: %w", w.Namespace, w.DeploymentName, err)
		}
		var replicas int32
		if dep.Spec.Replicas != nil {
			replicas = *dep.Spec.Replicas
		}
		podPhase := "None"
		pods, err := client.CoreV1().Pods(w.Namespace).List(ctx, metav1.ListOptions{
			LabelSelector: fmt.Sprintf("app.kubernetes.io/name=%s", w.Name),
			Limit:         1,
		})
		if err == nil && len(pods.Items) > 0 {
			podPhase = string(pods.Items[0].Status.Phase)
		}
		statuses = append(statuses, WorkloadStatus{
			Workload:      w,
			Replicas:      replicas,
			ReadyReplicas: dep.Status.ReadyReplicas,
			PodPhase:      podPhase,
		})
	}
	return statuses, nil
}

// ActivateWorkload scales the target workload to 1 and all others to 0.
func ActivateWorkload(ctx context.Context, client kubernetes.Interface, workloads []Workload, name string) error {
	found := false
	for _, w := range workloads {
		if w.Name == name {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("unknown workload: %s", name)
	}
	for _, w := range workloads {
		var target int32
		if w.Name == name {
			target = 1
		}
		if err := scaleDeployment(ctx, client, w.Namespace, w.DeploymentName, target); err != nil {
			return err
		}
	}
	return nil
}

// DeactivateAll scales all workloads to 0.
func DeactivateAll(ctx context.Context, client kubernetes.Interface, workloads []Workload) error {
	for _, w := range workloads {
		if err := scaleDeployment(ctx, client, w.Namespace, w.DeploymentName, 0); err != nil {
			return err
		}
	}
	return nil
}

func scaleDeployment(ctx context.Context, client kubernetes.Interface, namespace, name string, replicas int32) error {
	dep, err := client.AppsV1().Deployments(namespace).Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		return fmt.Errorf("get deployment %s/%s: %w", namespace, name, err)
	}
	dep.Spec.Replicas = &replicas
	_, err = client.AppsV1().Deployments(namespace).Update(ctx, dep, metav1.UpdateOptions{})
	if err != nil {
		return fmt.Errorf("update deployment %s/%s: %w", namespace, name, err)
	}
	return nil
}
