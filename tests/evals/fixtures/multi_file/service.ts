import { User } from "./types";
export function createUser(name: string): User {
  return { id: crypto.randomUUID(), name };
}
